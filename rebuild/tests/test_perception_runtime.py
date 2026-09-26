import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from unittest.mock import patch
import uuid

import pytest
from PIL import Image
from kcore.camera_manager import CameraConfig, CameraFrame, CameraManager, settled_thread
from kcore.local_faces import Face, LocalFaces, decode, encode, match, normalize
from kcore.perception import CaptureBudget, Occupancy, PerceptionController
from kcore.perception_store import PerceptionStore
from kcore.schema import ensure_schema
from kcore.sensors import TofStatus
from kcore.storage import KadencePaths
from kcore.vision import DeskVision


def run(coro): return asyncio.run(coro)
def vector(index=0): return tuple(1.0 if i==index else 0.0 for i in range(128))
def frame(generation=0):
    image=Image.new('RGB',(320,240)); output=io.BytesIO(); image.save(output,format='PNG')
    return CameraFrame(str(uuid.uuid4()),str(uuid.uuid4()),'unitv2-camera',output.getvalue(),320,240,time.time(),10,generation)

def tof(seq, distance=500, age=0, valid=True): return TofStatus('ready',seq,age,0,9,valid,distance if valid else None)


@pytest.fixture
def store(tmp_path):
    paths=KadencePaths.for_root(tmp_path); ensure_schema(paths)
    return PerceptionStore(paths.database)


def test_occupancy_debounce_hysteresis_and_cached_samples():
    occ=Occupancy()
    occ.update(tof(1),0); assert occ.state=='ARRIVAL_CANDIDATE'
    occ.update(tof(1),2); assert occ.state=='ARRIVAL_CANDIDATE'
    occ.update(tof(2),2.1); assert occ.state=='OCCUPIED'
    occ.update(tof(3,1000),3); assert occ.state=='OCCUPIED'
    occ.update(tof(4,1500),4); assert occ.state=='DEPARTURE_CANDIDATE'
    occ.update(tof(5,1500),6); assert occ.state=='DEPARTURE_CANDIDATE'
    occ.update(tof(6,1500),8.1); assert occ.state=='CLEAR'


@pytest.mark.parametrize('bad',[None,tof(3,age=4000),tof(3,valid=False)])
def test_bad_tof_is_unknown_not_clear(bad):
    occ=Occupancy();occ.update(tof(1),0);occ.update(tof(2),2.1)
    occ.update(bad,3)
    assert occ.state=='UNKNOWN'


def test_sequence_reset_and_long_sample_gap_redebounce():
    occ=Occupancy();occ.update(tof(10),0);occ.update(tof(11),2.1)
    occ.update(tof(1),3);assert occ.state=='ARRIVAL_CANDIDATE'
    occ.update(tof(2),5.2);assert occ.state=='OCCUPIED'
    occ.update(tof(3),50);assert occ.state=='ARRIVAL_CANDIDATE'


def test_automatic_budget_and_cooldown():
    budget=CaptureBudget()
    assert budget.reserve(0)
    assert not budget.reserve(1)
    assert budget.reserve(20)
    assert budget.reserve(40)
    assert not budget.reserve(59)
    assert budget.reserve(60)


def test_privacy_blocks_all_sources_and_voice_callback():
    async def case():
        called=[]
        async def capture(): called.append(True);return b''
        manager=CameraManager(capture,config=CameraConfig(privacy=True))
        for source in ('auto','unitv2-camera','robot-camera'):
            with pytest.raises(RuntimeError,match='privacy'): await manager.acquire(source=source,in_voice=capture)
        assert not called
    run(case())


def test_privacy_cancels_capture_without_publishing_or_overlapping_thread():
    async def case():
        entered=threading.Event(); released=threading.Event()
        def capture(*args,**kwargs): entered.set();released.wait(2);return b'invalid'
        async def robot(): raise AssertionError('No fallback after privacy')
        manager=CameraManager(robot)
        with patch('kcore.unitv2_network.start_camera_stream',capture):
            task=asyncio.create_task(manager.acquire(source='unitv2-camera'))
            await asyncio.to_thread(entered.wait,1)
            manager.configure(CameraConfig(privacy=True))
            assert manager._active is not None
            with pytest.raises(RuntimeError,match='privacy'): await manager.acquire()
            released.set()
            with pytest.raises(asyncio.CancelledError): await task
            assert manager._active is None
    run(case())


def test_auto_fallback_provenance_and_in_voice_owner():
    async def case():
        async def forbidden(): raise AssertionError('Must use in-turn callback')
        async def callback(): return b'\0'*(320*240*2)
        manager=CameraManager(forbidden)
        with patch('kcore.unitv2_network.start_camera_stream',side_effect=OSError()):
            result=await manager.acquire(in_voice=callback)
        assert result.source=='robot-camera' and result.width==320 and result.frame_id!=result.request_id
    run(case())


def test_manual_preempts_automatic_and_third_request_is_rejected():
    async def case():
        started=asyncio.Event(); finish=asyncio.Event(); count=0
        async def capture():
            nonlocal count
            count+=1
            if count==1:
                started.set()
                try: await asyncio.Event().wait()
                except asyncio.CancelledError: await finish.wait();raise
            return b'\0'*(320*240*2)
        manager=CameraManager(capture,config=CameraConfig(policy='EVENT_ONLY',source='robot-camera',perception_enabled=True))
        auto=asyncio.create_task(manager.acquire(purpose='automatic'));await started.wait()
        manual=asyncio.create_task(manager.acquire());await asyncio.sleep(.01)
        with pytest.raises(RuntimeError,match='busy'): await manager.acquire()
        finish.set()
        with pytest.raises(asyncio.CancelledError): await auto
        assert (await manual).source=='robot-camera'
    run(case())


def test_camera_deadline_and_backoff_prevent_restart_storm():
    async def case():
        count=0
        async def robot():
            nonlocal count
            count+=1;await asyncio.sleep(1)
        manager=CameraManager(robot)
        for _ in range(2):
            with pytest.raises(RuntimeError,match='unavailable'):await manager.acquire(source='robot-camera',timeout=.01)
        assert count==1
    run(case())


def test_private_preview_cannot_describe_or_save():
    async def case():
        vision=DeskVision();vision.accept_frame(frame())
        def guard():raise RuntimeError('privacy')
        vision.guard=guard
        with pytest.raises(RuntimeError,match='privacy'):await vision.describe('x',None)
        with pytest.raises(RuntimeError,match='privacy'):await vision.save(None,None,1)
    run(case())


def test_corrupt_settings_fail_closed(tmp_path):
    (tmp_path/'camera-settings.json').write_text('{broken')
    assert CameraConfig.load(tmp_path).privacy
    config=CameraConfig(policy='AWARE',privacy=True);config.save(tmp_path)
    assert CameraConfig.load(tmp_path)==config


def test_embedding_validation_and_person_level_margin():
    for bad in ([0]*128,[float('nan')]*128,[1e308]*128,[1]*127):
        with pytest.raises(ValueError):normalize(bad)
    assert decode(encode(vector()))==vector()
    assert match(vector(),[('a',vector()),('a',vector())])==('a','candidate')
    assert match(vector(),[('a',vector()),('b',vector())])==(None,'ambiguous')
    assert match(vector(2),[('a',vector())])==(None,'unresolved')


def test_enrollment_compatibility_and_forget_removes_biometrics(store):
    person=store.call('enroll',name='Boss',vectors=[vector()]*3)
    assert len(store.call('profiles'))==3
    with pytest.raises(ValueError):store.call('enroll',name='Boss',vectors=[vector()]*3)
    store.call('forget',person=person)
    assert store.call('profiles')==[] and store.call('persons')==[]
    with sqlite3.connect(store.database) as db:assert db.execute('SELECT count(*) FROM face_profiles').fetchone()[0]==0


def test_actions_claim_once_concurrently_and_restart_marks_uncertain(store):
    person=store.call('enroll',name='Boss',vectors=[vector()]*3)
    run_id=store.call('begin',fingerprint='test')
    f=frame()
    session=store.call('observe',run=run_id,person=person,frame=f,trigger='arrival',action='greeting')
    assert store.call('observe',run=run_id,person=person,frame=f,trigger='arrival',action='greeting')==session
    with ThreadPoolExecutor(max_workers=2) as pool:
        actions=list(pool.map(lambda _:store.call('claim',run=run_id,greetings=True,unknown_alerts=True),range(2)))
    assert sum(x is not None for x in actions)==1
    store.call('begin',fingerprint='restarted')
    with sqlite3.connect(store.database) as db:
        assert db.execute('SELECT state FROM perception_actions').fetchone()[0]=='uncertain'
        assert db.execute('SELECT ended_at FROM presence_sessions WHERE id=?',(session,)).fetchone()[0]==f.captured_at


def test_unknown_sessions_are_independent_and_expired_actions_suppressed(store):
    run_id=store.call('begin',fingerprint='test')
    f=replace(frame(),captured_at=time.time()-30)
    one=store.call('observe',run=run_id,person=None,frame=f,trigger='arrival',action='unknown_alert')
    two=store.call('observe',run=run_id,person=None,frame=f,trigger='arrival',action='unknown_alert')
    assert one!=two
    assert store.call('claim',run=run_id,greetings=True,unknown_alerts=True) is None
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT count(*) FROM perception_actions WHERE state='suppressed'").fetchone()[0]==2


def test_sensor_evidence_cannot_extend_visual_identity(store):
    run_id=store.call('begin',fingerprint='test');old=replace(frame(),captured_at=time.time()-190)
    session=store.call('observe',run=run_id,person=None,frame=old,trigger='arrival')
    store.call('event',run=run_id,kind='occupancy',trigger='tof',evidence={'state':'OCCUPIED'})
    store.call('expire',run=run_id,cutoff=time.time()-180)
    with sqlite3.connect(store.database) as db:
        assert db.execute('SELECT ended_at FROM presence_sessions WHERE id=?',(session,)).fetchone()[0]==old.captured_at


def test_same_run_links_enforced(store):
    one=store.call('begin',fingerprint='one')
    session=store.call('observe',run=one,person=None,frame=frame(),trigger='arrival')
    two=store.call('begin',fingerprint='two')
    with pytest.raises(ValueError):store.call('event',run=two,kind='subject_seen',trigger='arrival',session=session)


def test_two_frames_confirm_multiple_people_without_saving_images(tmp_path):
    async def case():
        paths=KadencePaths.for_root(tmp_path);ensure_schema(paths)
        async def unused():raise AssertionError()
        camera=CameraManager(unused,config=CameraConfig(policy='EVENT_ONLY',perception_enabled=True))
        camera.unitv2.verified=True
        async def acquire(**kwargs):return frame(camera.generation)
        camera.acquire=acquire
        class Faces:
            health='ready'
            def analyze(self,png):return (Face((0,0,.3,.4),vector(),1),Face((.5,0,.3,.4),vector(1),1))
        notices=[]
        async def deliver(action,check):check();notices.append(action)
        controller=PerceptionController(camera,paths,lambda *args:None,deliver,lambda:False,faces=Faces())
        await controller.start()
        person=await controller.db('enroll',name='Boss',vectors=[vector()]*3)
        await controller._burst('gesture')
        with sqlite3.connect(paths.database) as db:
            rows=db.execute('SELECT person_id,identity_status FROM presence_sessions WHERE ended_at IS NULL').fetchall()
            assert (person,'confirmed') in rows and (None,'unresolved') in rows and len(rows)==2
            assert db.execute('SELECT count(*) FROM media').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM perception_actions').fetchone()[0]==0
        await controller.close()
        assert not list(paths.images_dir.rglob('*.png'))
    run(case())


def test_policy_off_rejects_automatic_but_allows_manual():
    async def case():
        async def robot():return b'\0'*(320*240*2)
        manager=CameraManager(robot,config=CameraConfig(source='robot-camera'))
        with pytest.raises(RuntimeError,match='off'):await manager.acquire(purpose='automatic')
        assert (await manager.acquire()).source=='robot-camera'
    run(case())


def test_real_packaged_models_load_and_run_locally(tmp_path):
    model_dir=os.environ.get('KADENCE_TEST_MODELS')
    if not model_dir:pytest.skip('Pinned models exercised by the Windows package job')
    model=LocalFaces(tmp_path);model.directory=Path(model_dir)
    assert model.analyze(frame().png)==()
    assert model.health=='ready'
    import numpy as np
    feature=model._recognizer.feature(np.zeros((112,112,3),dtype=np.uint8)).reshape(-1)
    assert len(normalize(feature))==128


def test_repeated_cancellation_keeps_worker_owned_until_settled():
    async def case():
        started=threading.Event();finish=threading.Event()
        def operation():started.set();finish.wait(2);return 1
        task=asyncio.create_task(settled_thread(operation))
        await asyncio.to_thread(started.wait,1)
        task.cancel();await asyncio.sleep(.01)
        task.cancel();await asyncio.sleep(.01)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):await task
    run(case())
