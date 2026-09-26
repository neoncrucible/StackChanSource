import asyncio
from dataclasses import asdict, replace
import json
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from kcore.camera_manager import CameraConfig, CameraFrame, CameraManager
from kcore.desktop_worker import DesktopController
from kcore.local_faces import Face
from kcore.perception import PerceptionController, diagnostic_decision, diagnostic_state
from kcore.schema import ensure_schema
from kcore.sensor_sampler import SensorSampler
from kcore.sensors import GestureStatus, TofStatus
from kcore.storage import KadencePaths


def vector(index=0):return tuple(float(i==index) for i in range(128))
def tof(seq,distance=600):return TofStatus('ready',seq,0,0,9,True,distance)
def gesture(seq):return GestureStatus('ready',seq+1,0,seq,0,1)


async def controller(root, *, policy='EVENT_ONLY', enabled=True, source='robot-camera', greetings=False, notices=False):
    paths=KadencePaths.for_root(root);ensure_schema(paths)
    now=[0.0];busy=[False];events=[];delivered=[]
    camera=CameraManager(None,config=CameraConfig(policy=policy,source=source,perception_enabled=enabled,greetings=greetings,unknown_alerts=notices))
    async def capture(**kw):
        return CameraFrame(str(uuid.uuid4()),str(uuid.uuid4()),source,b'local-test-frame',320,240,time.time(),10,camera.generation)
    camera.acquire=AsyncMock(side_effect=capture)
    faces=SimpleNamespace(health='ready',analyze=lambda _: (Face((0,0,.5,.5),vector(),1),))
    async def deliver(action,check):check();delivered.append(action)
    sampler=SensorSampler(lambda *a:events.append(a),clock=lambda:now[0])
    pc=PerceptionController(camera,paths,lambda *a:events.append(a),deliver,lambda:busy[0],faces=faces,clock=lambda:now[0],sampler=sampler)
    await pc.start()
    pc._ticker.cancel()
    with __import__('contextlib').suppress(asyncio.CancelledError):await pc._ticker
    pc._ticker=None
    return SimpleNamespace(pc=pc,camera=camera,now=now,busy=busy,events=events,delivered=delivered,paths=paths,faces=faces)


async def sample(env,second,seq,distance=600,gest=0):
    env.now[0]=second
    await env.pc.sample(env.pc.sampler.sample(tof(seq,distance),gesture(gest)))


def test_arrival_once_background_quiet_and_no_saved_images(tmp_path):
    async def case():
        e=await controller(tmp_path)
        await sample(e,0,1);await sample(e,1,2);await sample(e,2.1,3)
        await e.pc.task
        for i in range(4,40):await sample(e,i,i,600+(i%3)*50)
        assert e.camera.acquire.await_count==2 and e.pc._completed_bursts==1
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT count(*) FROM media').fetchone()[0]==0
            assert db.execute("SELECT count(*) FROM perception_events WHERE event_type='capture_result'").fetchone()[0]==1
        await e.pc.close()
        assert not list(e.paths.images_dir.rglob('*.png'))
    asyncio.run(case())


@pytest.mark.parametrize('reason',['not_enabled','privacy','off','unverified','stopped'])
def test_every_activation_gate_prevents_camera_work(tmp_path,reason):
    async def case():
        e=await controller(tmp_path,enabled=reason!='not_enabled',policy='OFF' if reason=='off' else 'EVENT_ONLY',source='unitv2-camera' if reason=='unverified' else 'robot-camera')
        if reason=='privacy':e.camera.configure(replace(e.camera.config,privacy=True))
        if reason=='stopped':e.camera.unitv2.mode='STOPPED'
        assert not e.pc.request('gesture')
        e.camera.acquire.assert_not_called()
        await e.pc.close()
    asyncio.run(case())


def test_gesture_requests_two_frames_when_tof_is_unknown_and_cooldown_suppresses_repeat(tmp_path):
    async def case():
        e=await controller(tmp_path)
        await e.pc.sample(e.pc.sampler.sample(None,gesture(0)))
        e.now[0]=1;await e.pc.sample(e.pc.sampler.sample(None,gesture(1)))
        await e.pc.task
        e.now[0]=5;await e.pc.sample(e.pc.sampler.sample(None,gesture(2)))
        assert e.camera.acquire.await_count==2 and e.pc.pending is None
        assert any(d.get('reason')=='cooldown' for n,d in e.events if n=='perception_decision')
        assert not e.pc.request('made_up_event')
        await e.pc.close()
    asyncio.run(case())


def test_voice_defers_one_arrival_then_processes_it_without_extending_deadline(tmp_path):
    async def case():
        e=await controller(tmp_path);e.busy[0]=True
        await sample(e,0,1);await sample(e,2.1,2)
        assert e.pc.pending['trigger']=='arrival' and e.camera.acquire.await_count==0
        expiry=e.pc.pending['expires']
        for second in range(3,8):
            e.now[0]=second;e.pc.request('gesture')
        assert e.pc.pending['expires']==expiry
        e.busy[0]=False;e.now[0]=3;await e.pc.tick()
        await e.pc.task
        assert e.camera.acquire.await_count==2 and e.pc.pending is None
        await e.pc.close()
    asyncio.run(case())


def test_deferred_event_expires_and_privacy_clears_pending(tmp_path):
    async def case():
        e=await controller(tmp_path);e.busy[0]=True
        e.pc.request('gesture');assert e.pc.pending
        e.now[0]=6;await e.pc.tick();assert e.pc.pending is None
        e.pc.request('gesture');e.camera.configure(replace(e.camera.config,privacy=True))
        await e.pc.reset('privacy');assert e.pc.pending is None
        e.camera.acquire.assert_not_called()
        await e.pc.close()
    asyncio.run(case())


def test_camera_released_before_optional_greeting_and_once_per_occupancy_visit(tmp_path):
    async def case():
        e=await controller(tmp_path,greetings=True)
        person=await e.pc.db('enroll',name='Boss',vectors=[vector()]*3)
        releases=[]
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def burst():
            try:yield
            finally:releases.append('stopped')
        e.camera.unitv2.burst=burst
        async def deliver(action,check):
            assert releases and releases[-1]=='stopped'
            check();e.delivered.append(action)
        e.pc.deliver=deliver
        assert e.pc.request('gesture');await e.pc.task
        assert len(e.delivered)==1 and person in e.pc._visit_greeted
        # Even after visual evidence expires, the ongoing occupancy visit does not re-greet.
        await e.pc.db('expire',run=e.pc.run,cutoff=float('inf'))
        e.pc._tracks.clear();e.now[0]=400
        assert e.pc.request('gesture');await e.pc.task
        assert len(e.delivered)==1
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT count(*) FROM perception_actions').fetchone()[0]==1
        await e.pc.close()
    asyncio.run(case())


def test_ambiguous_known_face_is_not_announced_as_unenrolled(tmp_path):
    async def case():
        e=await controller(tmp_path,greetings=True,notices=True)
        for name in ('one','two'):await e.pc.db('enroll',name=name,vectors=[vector()]*3)
        e.pc.request('gesture');await e.pc.task
        assert not e.delivered
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT identity_status FROM presence_sessions').fetchone()[0]=='ambiguous'
            assert db.execute('SELECT count(*) FROM perception_actions').fetchone()[0]==0
        await e.pc.close()
    asyncio.run(case())


@pytest.mark.parametrize('policy',['EVENT_ONLY','AWARE'])
def test_heartbeat_is_sparse_and_aware_only(tmp_path,policy):
    async def case():
        e=await controller(tmp_path,policy=policy)
        await sample(e,0,1);await sample(e,2.1,2);await e.pc.task
        for i in range(3,124):
            await sample(e,float(i),i);await e.pc.tick()
        if e.pc.task:await e.pc.task
        assert e.camera.acquire.await_count==(4 if policy=='AWARE' else 2)
        await e.pc.close()
    asyncio.run(case())


def test_privacy_during_burst_cancels_without_identity_or_action(tmp_path):
    async def case():
        e=await controller(tmp_path,greetings=True,notices=True)
        entered=asyncio.Event()
        async def waiting(**kwargs):entered.set();await asyncio.Event().wait()
        e.camera.acquire=AsyncMock(side_effect=waiting)
        e.pc.request('gesture');await entered.wait()
        e.camera.configure(replace(e.camera.config,privacy=True));await e.pc.interrupt()
        with sqlite3.connect(e.paths.database) as db:
            assert db.execute('SELECT count(*) FROM presence_sessions').fetchone()[0]==0
            assert db.execute('SELECT count(*) FROM perception_actions').fetchone()[0]==0
        assert not e.delivered
        await e.pc.close()
    asyncio.run(case())


def test_automatic_source_never_falls_into_unmanaged_factory_capture():
    async def case():
        async def robot():return b'\0'*(320*240*2)
        manager=CameraManager(robot,config=CameraConfig(policy='EVENT_ONLY',perception_enabled=True))
        manager.unitv2.verified=True
        manager.unitv2.key_loader=lambda:None
        with patch('kcore.unitv2_network.start_camera_stream',side_effect=AssertionError('No legacy automatic camera access')) as legacy:
            result=await manager.acquire(purpose='automatic')
        assert result.source=='robot-camera';legacy.assert_not_called()
        await manager.close()
    asyncio.run(case())


def test_worker_refuses_unverified_autonomy_without_persisting_opt_in(tmp_path):
    async def case():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        values=asdict(CameraConfig(policy='EVENT_ONLY',perception_enabled=True))
        with pytest.raises(ValueError,match='TEST START / STOP'):await worker.command('camera_settings',values)
        assert not CameraConfig.load(tmp_path).perception_enabled
        await worker.close()
    asyncio.run(case())


def test_diagnostics_exclude_names_images_and_embeddings():
    safe=diagnostic_state({'gate':'ready','privacy':False,'health':'private-name','subjects':1,'name':'Boss','embedding':[1],'image':'private'})
    assert safe=={'gate':'ready','subjects':1,'privacy':False}
    assert diagnostic_decision({'trigger':'arrival','decision':'completed','reason':'captured','name':'Boss'})=={'trigger':'arrival','decision':'completed','reason':'captured'}


def test_console_opt_in_gate_and_sanitized_decisions(tmp_path):
    from PySide6.QtWidgets import QApplication
    from kcore.desktop_ui import MainWindow
    qt=QApplication.instance() or QApplication([])
    window=MainWindow(directory=tmp_path,load_credentials=False)
    try:
        assert not window.perception_enable.isChecked()
        values=asdict(CameraConfig(policy='EVENT_ONLY',perception_enabled=True))
        window.on_event('camera_settings',values)
        with patch.object(window.control,'send') as send:
            window.apply_camera_policy()
            assert send.call_args.args==('camera_settings',values)
        window.on_event('perception',{'gate':'ready','completed_bursts':2,'bursts':2,'health':'ready','name':'private-name','confirmed_persons':['private-id']})
        window.on_event('perception_decision',{'trigger':'gesture','decision':'completed','reason':'captured','image':'private-image'})
        assert 'enabled' in window.perception_gate.text() and 'VISION GESTURE' in window.reflex_log.toPlainText()
        assert 'private' not in json.dumps(window.perception_snapshot)
        assert 'private' not in json.dumps(list(window.perception_decisions))
    finally:window.ticker.stop();window.quitting=True;window.close()
