"""Movement, measured training coverage, identity ambiguity and real persistence."""
import asyncio
from dataclasses import replace
import json
import sqlite3
from unittest.mock import patch

import pytest

from kcore.face_sequence import FaceSequence, LiveEnrollment, recognition_diagnostic
from kcore.local_faces import Face, normalize
from kcore.perception import LookInterrupted
from test_autonomous_perception import controller, vector


def training_face(index):
    stage = min(index//4,4)
    v = list(vector()); v[5+index%20] = .12
    return Face((.1,.1,.35 if stage==4 else .5,.5),normalize(v),.99,
        (0,.24,-.24,0,0)[stage],.7 if stage==3 else .5)


def install_training(e):
    count = [0]
    def analyze(_):
        face = training_face(count[0]); count[0] += 1
        return (face,)
    e.faces.analyze = analyze


@pytest.fixture
def fast_face_clock(monkeypatch):
    """Only pacing is accelerated; real camera/DB ownership still runs."""
    original = asyncio.sleep
    async def sleep(delay, *args, **kwargs):
        return await original(0 if delay==.5 else delay, *args, **kwargs)
    monkeypatch.setattr('kcore.perception.asyncio.sleep',sleep)


def test_multi_view_training_requires_measured_angles_and_distance():
    training = LiveEnrollment()
    assert training.offer([training_face(0)],{'detected':1,'usable':1})[0]
    for _ in range(10):
        assert not training.offer([training_face(0)],{'detected':1,'usable':1})[0]
    assert len(training.faces)==1
    # Different face: no anchor drift and no sample accepted.
    assert not training.offer([replace(training_face(1),embedding=vector(100))],{'detected':1,'usable':1})[0]
    assert not training.offer([training_face(1)],{'detected':2,'usable':1})[0]
    for index in range(1,20):
        if index in (4,8,12,16):
            assert not training.offer([replace(training_face(index),yaw=0,pitch=.5,box=(.1,.1,.5,.5))],{'detected':1,'usable':1})[0]
        assert training.offer([training_face(index)],{'detected':1,'usable':1})[0]
    assert training.done and set(training.views)==set(training.VIEWS)


def test_side_views_match_same_profile_without_near_identical_frame_gate():
    a = Face((.1,.1,.4,.5),vector(),.99)
    b = replace(a,box=(.2,.1,.4,.5),embedding=normalize([.5,.866]+[0]*126))
    sequence = FaceSequence([('person',a.embedding),('person',b.embedding)])
    assert not sequence.update([a])[0]['person']
    assert sequence.update([b])[0]['person']=='person'


def test_blink_recovery_cannot_reuse_evidence_after_long_gap():
    face = training_face(0)
    sequence = FaceSequence([('person',face.embedding)])
    sequence.update([face]); sequence.update([]); sequence.update([replace(face,box=(.2,.1,.5,.5))])
    assert sequence.confirmed=={'person'}
    for _ in range(3): sequence.update([])
    sequence.update([face]); assert not sequence.confirmed


def test_competing_profiles_and_duplicate_candidates_are_never_confirmed():
    face = training_face(0)
    sequence = FaceSequence([('one',face.embedding),('two',face.embedding)])
    for _ in range(6): sequence.update([face])
    assert not sequence.confirmed and sequence.current[0]['identity']=='ambiguous'
    sequence = FaceSequence([('one',face.embedding)])
    for _ in range(6): sequence.update([face,replace(face,box=(.6,.1,.3,.5))])
    assert not sequence.confirmed
    assert all(t['match']['reason']=='duplicate_identity' for t in sequence.current)


def test_profile_switch_requires_new_consensus_and_unknown_cannot_inherit_name():
    a=training_face(0)
    b=replace(a,embedding=normalize([.7,.714]+[0]*126))
    sequence=FaceSequence([('one',a.embedding),('two',b.embedding)])
    sequence.update([a]); sequence.update([b]); sequence.update([b])
    assert not sequence.confirmed
    sequence.update([b]); assert sequence.confirmed=={'two'}
    sequence.update([replace(b,embedding=vector(100))]); assert not sequence.confirmed


def test_live_enrollment_and_all_profiles_survive_database_reopen(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,enabled=False)
        install_training(e)
        result=await e.pc.enroll('Test profile')
        assert result['samples']==20 and e.camera.acquire.await_count==20
        assert len(await e.pc.db('profiles'))==20
        assert [d['sample'] for n,d in e.events if n=='enrollment' and d['state']=='accepted']==list(range(1,21))
        # Previously the 96-row query silently hid later profiles once sample counts grew.
        for index in range(5): await e.pc.db('enroll',name=f'Profile {index}',vectors=[vector(index+1)]*20)
        from kcore.perception_store import PerceptionStore
        assert len(PerceptionStore(e.paths.database).call('profiles'))==120
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT count(*) FROM media').fetchone()[0]==0
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        await e.pc.close()
    asyncio.run(case())


def test_blur_and_missing_face_wait_without_discarding_training(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,enabled=False)
        count=[-2]
        def details(_):
            i=count[0]; count[0]+=1
            return ((),{'detected':int(i==-1),'usable':0,'blurred':int(i==-1)}) if i<0 else ((training_face(i),),{'detected':1,'usable':1})
        e.faces.analyze_details=details
        result=await e.pc.enroll('Test profile')
        assert result['samples']==20 and e.camera.acquire.await_count==22
        assert any(n=='enrollment' and d['state']=='waiting' for n,d in e.events)
        await e.pc.close()
    asyncio.run(case())


def test_automatic_movement_confirms_then_releases_and_greets_once(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,greetings=True)
        a=training_face(0); b=replace(a,embedding=normalize([.5,.866]+[0]*126))
        person=await e.pc.db('enroll',name='Test profile',vectors=[a.embedding,b.embedding,a.embedding])
        frames=iter([(a,),(),(b,)])
        e.faces.analyze=lambda _:next(frames)
        assert e.pc.request('gesture'); await e.pc.task
        assert len(e.delivered)==1 and e.delivered[0]['person_id']==person
        assert e.pc.health=='ready' and e.camera.acquire.await_count==3
        evidence=[d for n,d in e.events if n=='recognition_evidence']
        assert evidence[-1]['confirmed']==1 and evidence[-1]['frames']==3
        await e.pc.close()
    asyncio.run(case())


def test_interrupted_look_always_has_terminal_status(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path)
        original=e.pc._face_evidence
        async def interrupted(*a,**kw):
            result=await original(*a,**kw);e.busy[0]=True;return result
        e.pc._face_evidence=interrupted
        assert e.pc.request('gesture');await e.pc.task
        decisions=[d for n,d in e.events if n=='perception_decision']
        assert decisions[-1]=={'trigger':'gesture','decision':'cancelled','reason':'voice_busy'}
        assert e.pc.health=='idle' and not e.delivered
        e.busy[0]=False;e.now[0]=21;e.pc._face_evidence=original
        assert e.pc.request('gesture');await e.pc.task
        assert e.pc.health=='ready'
        await e.pc.close()
    asyncio.run(case())


def test_explicit_live_check_keeps_sampling_after_success_and_never_greets(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,enabled=False,greetings=True)
        await e.pc.db('enroll',name='Test profile',vectors=[vector()]*3)
        result=await e.pc.test_recognition(live=True)
        assert result['frames']==20 and result['seen_names']==['Test profile']
        assert not e.delivered
        await e.pc.close()
    asyncio.run(case())


def test_recognition_diagnostics_are_numeric_or_enumerated_only():
    safe=recognition_diagnostic({'kind':'test','reason':'below_threshold','score':.45,'gap':float('nan'),'usable':1,
        'name':'Private name','person':'secret-id','embedding':[1]*128,'png_base64':'image','view':'private text'})
    assert safe=={'kind':'test','reason':'below_threshold','score':.45,'usable':1}


def test_arrival_gets_only_one_bounded_followup_before_greeting(tmp_path,fast_face_clock):
    async def case():
        e=await controller(tmp_path,greetings=True)
        await e.pc.db('enroll',name='Test profile',vectors=[vector(1)]*3)
        e.pc.occupancy.state='OCCUPIED'
        assert e.pc.request('arrival'); await e.pc.task
        assert e.pc._arrival_retry and not e.delivered
        e.now[0]=10; await e.pc.tick()
        e.now[0]=20; await e.pc.tick(); await e.pc.task
        assert e.pc._completed_bursts==2 and e.pc._arrival_retry is None
        assert e.pc._arrival_retried
        e.now[0]=21; await e.pc.tick(); assert e.pc._completed_bursts==2
        await e.pc.close()
    asyncio.run(case())


def test_pinned_native_models_on_disjoint_video_views_and_other_people():
    import os
    from kcore.face_validation import replay_check
    models=os.environ.get('KADENCE_TEST_MODELS')
    fixtures=os.environ.get('KADENCE_TEST_FACE_FIXTURES')
    if not models or not fixtures:pytest.skip('Pinned video and face models supplied by release CI')
    result=replay_check(fixtures,models=models)
    assert result['matched_views']>result['three_sample_matches']


def test_blur_measure_is_contrast_relative_but_rejects_real_smoothing(tmp_path):
    import numpy as np
    import cv2
    from types import SimpleNamespace
    from kcore.local_faces import LocalFaces
    from test_face_review import photo
    model=LocalFaces(tmp_path)
    model._detector=SimpleNamespace(setInputSize=lambda _:None,detect=lambda _:(None,np.array([[0,0,90,90,*([0]*10),.99]],dtype=np.float32)))
    # Sharp low-contrast texture versus the same texture after heavy smoothing.
    rng=np.random.default_rng(70)
    gray=rng.integers(30,38,(112,112),dtype=np.uint8)
    crop=np.repeat(gray[:,:,None],3,axis=2)
    model._recognizer=SimpleNamespace(alignCrop=lambda *_:crop,feature=lambda _:np.array(vector()))
    assert len(model.analyze_details(photo()['png'])[0])==1
    crop=cv2.GaussianBlur(crop,(31,31),9)
    assert model.analyze_details(photo()['png'])[1]['blurred']==1
