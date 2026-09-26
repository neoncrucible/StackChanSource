import ast
import asyncio
import base64
from dataclasses import asdict
import hashlib
import hmac
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from PIL import Image
from kcore.camera_manager import CameraConfig, CameraManager
from kcore.unitv2_lifecycle import Client, LifecycleError, UnitV2Owner

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'unitv2'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


bridge=module('kadence_unitv2')
installer=module('install_unitv2')
KEY='ab'*32


def jpeg():
    output=io.BytesIO();Image.new('RGB',(32,24),'green').save(output,'JPEG')
    return output.getvalue()


@pytest.fixture
def producer(tmp_path):
    child=tmp_path/'camera.py'
    child.write_text("import sys,time,json\nsys.stdin.readline()\nprint('vendor banner',flush=True)\nwhile True:\n print(json.dumps({'img':"+repr(base64.b64encode(jpeg()).decode())+"}),flush=True)\n time.sleep(.04)\n")
    camera=bridge.Producer([sys.executable,str(child)],str(tmp_path))
    yield camera
    camera.close()


@pytest.fixture
def service(producer):
    server=bridge.Server(('127.0.0.1',0),bridge.CameraService(producer,KEY))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    yield server,Client('127.0.0.1',KEY,port=server.server_port)
    server.shutdown();server.server_close();thread.join(2)


def test_real_process_fresh_frames_stop_and_restart(service,producer):
    server,client=service
    assert client.call('status')['stop_confirmed']
    lease=uuid.uuid4().hex
    client.call('start',lease)
    first,seq=client.call('frame',lease)
    second,next_seq=client.call('frame',lease)
    assert first==second==jpeg() and next_seq>seq
    child=producer.process
    stopped=client.call('stop',lease)
    assert stopped['stop_confirmed'] and child.poll() is not None and producer.frame is None
    with pytest.raises(LifecycleError):client.call('start',lease)
    other=uuid.uuid4().hex
    client.call('start',other);client.call('frame',other)
    assert client.call('stop',other)['stops']==2


def test_second_owner_cannot_take_or_stop_first(service,producer):
    _,client=service
    one,two=uuid.uuid4().hex,uuid.uuid4().hex
    client.call('start',one)
    with pytest.raises(LifecycleError):client.call('start',two)
    with pytest.raises(LifecycleError):client.call('stop',two)
    assert client.call('status')['lease']==one
    assert client.call('stop')['stop_confirmed']  # Explicit authenticated stop all.


def test_lease_expiry_reaps_actual_child_without_host(producer):
    now=[100.0];producer.clock=lambda:now[0]
    lease=uuid.uuid4().hex;producer.start(lease)
    child=producer.process
    now[0]=131;producer.watchdog_once()
    assert child.poll() is not None
    status=producer.status()
    assert status['stop_confirmed'] and status['expirations']==1
    with pytest.raises(bridge.CameraError):producer.start(lease)


def test_snapshot_wait_is_woken_by_stop(producer):
    # Hold the reader without sending frames: stop must wake the waiting request.
    producer.command=[sys.executable,'-c','import time;time.sleep(60)']
    lease=uuid.uuid4().hex;producer.start(lease)
    errors=[]
    def get_frame():
        try:producer.snapshot(lease)
        except bridge.CameraError as exc:errors.append(exc.reason)
    waiter=threading.Thread(target=get_frame);waiter.start()
    producer.stop(lease);waiter.join(2)
    assert not waiter.is_alive() and errors


def test_conflicting_unowned_producer_is_never_claimed_stopped(producer):
    producer.foreign=lambda pid:True
    assert not producer.status()['stop_confirmed']
    with pytest.raises(bridge.CameraError,match='other_camera_producer'):producer.start(uuid.uuid4().hex)
    with pytest.raises(bridge.CameraError):producer.stop()
    producer.foreign=lambda pid:False


def test_challenges_are_signed_single_use_bounded_and_expire(producer):
    now=[10.0];service=bridge.CameraService(producer,KEY,clock=lambda:now[0])
    nonce=service.challenge()['nonce']
    raw=json.dumps({'nonce':nonce,'operation':'start','lease':uuid.uuid4().hex}).encode()
    sign=hmac.new(bytes.fromhex(KEY),raw,hashlib.sha256).hexdigest()
    with pytest.raises(bridge.CameraError):service.authenticate(raw,'wrong')
    assert service.authenticate(raw,sign)['operation']=='start'
    with pytest.raises(bridge.CameraError):service.authenticate(raw,sign)
    for _ in range(32):service.challenge()
    with pytest.raises(bridge.CameraError):service.challenge()
    now[0]=21
    assert service.challenge()['nonce']


def test_bad_pairing_never_starts_camera(service,producer):
    server,_=service
    wrong=Client('127.0.0.1','cd'*32,port=server.server_port)
    with pytest.raises(LifecycleError,match='pairing rejected'):wrong.call('start',uuid.uuid4().hex)
    assert producer.starts==0


def test_manager_managed_capture_releases_producer_and_privacy_blocks(service):
    server,_=service
    async def case():
        events=[]
        camera=CameraManager(None,emit=lambda *args:events.append(args))
        camera.unitv2=UnitV2Owner(camera.emit,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        frame=await camera.acquire(source='unitv2-camera',address='127.0.0.1')
        assert frame.width==32 and camera.unitv2.status['stop_confirmed']
        camera.configure(CameraConfig(privacy=True))
        with pytest.raises(RuntimeError,match='privacy'):await camera.unitv2_control('KEEP_READY')
        with pytest.raises(RuntimeError,match='privacy'):await camera.acquire()
        await camera.close()
        assert events[-1][0]=='unitv2_lifecycle'
    asyncio.run(case())


def test_keep_ready_single_process_and_on_demand_releases(service):
    server,_=service
    async def case():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        await owner.control_mode('KEEP_READY','127.0.0.1')
        await owner.capture('127.0.0.1');await owner.capture('127.0.0.1')
        status=await owner.refresh('127.0.0.1')
        assert status['starts']==1 and status['producer_running']
        await owner.control_mode('ON_DEMAND','127.0.0.1')
        assert owner.status['stop_confirmed'] and owner.heartbeat is None
        await owner.close()
    asyncio.run(case())


def test_cancellation_waits_for_network_then_stops_and_never_returns_image():
    async def case():
        entered,released=threading.Event(),threading.Event();calls=[]
        class Stub:
            address='127.0.0.1'
            def interrupt(self):pass
            def call(self,op,lease=None,timeout=None,cancel=None):
                calls.append(op)
                if op=='start':entered.set();released.wait(2)
                return {'state':'STOPPED' if op=='stop' else 'STARTING','stop_confirmed':op=='stop'}
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda *a:Stub())
        task=asyncio.create_task(owner.capture('127.0.0.1'))
        await asyncio.to_thread(entered.wait,1);task.cancel();await asyncio.sleep(.01)
        assert not task.done()
        released.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert calls==['start','stop'] and owner.status['stop_confirmed']
    asyncio.run(case())


def test_burst_shares_lease_then_releases(service):
    server,_=service
    async def case():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        async with owner.burst():
            await owner.capture('127.0.0.1');await owner.capture('127.0.0.1')
            assert owner.status['producer_running']
        status=await owner.refresh('127.0.0.1')
        assert status['starts']==1 and status['stops']==1 and status['stop_confirmed']
        await owner.close()
    asyncio.run(case())


def test_cancel_interrupts_blocked_real_http_frame_without_waiting_for_timeout(service,producer):
    server,_=service
    producer.command=[sys.executable,'-c','import time;time.sleep(60)']
    async def case():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        task=asyncio.create_task(owner.capture('127.0.0.1'))
        for _ in range(100):
            if producer.process is not None:break
            await asyncio.sleep(.01)
        await asyncio.sleep(.1)
        started=time.monotonic();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert time.monotonic()-started<2
        assert producer.status()['stop_confirmed']
        await owner.close()
    asyncio.run(case())


def test_stop_mode_survives_unrelated_settings_reconciliation(service):
    server,_=service
    async def case():
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        await owner.control_mode('STOPPED','127.0.0.1')
        await owner.stop('127.0.0.1')
        assert owner.mode=='STOPPED' and owner.status['stop_confirmed']
        await owner.close()
    asyncio.run(case())


def test_stop_failure_is_reported_not_claimed_as_success():
    async def case():
        class Stub:
            address='127.0.0.1'
            def call(self,*a,**k):raise TimeoutError()
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda *a:Stub())
        with pytest.raises(TimeoutError):await owner.control_mode('STOPPED','127.0.0.1')
        assert owner.status['state']=='STOP_UNCONFIRMED' and not owner.status['stop_confirmed']
    asyncio.run(case())


def test_lifecycle_proof_survives_restart_but_not_a_new_pairing(service,tmp_path):
    server,_=service
    async def case():
        factory=lambda a,k:Client(a,k,port=server.server_port)
        owner=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=factory)
        await owner.capture('127.0.0.1')
        owner.record_verified(tmp_path)
        reopened=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=factory)
        reopened.verification_root=tmp_path
        await reopened.refresh('127.0.0.1')
        assert reopened.verified
        wrong=UnitV2Owner(lambda *a:None,key_loader=lambda:'cd'*32,client_factory=factory)
        wrong.verification_root=tmp_path
        with pytest.raises(LifecycleError):await wrong.refresh('127.0.0.1')
        assert not wrong.verified
        await owner.close();await reopened.close()
    asyncio.run(case())


def test_lifecycle_diagnostics_never_include_credentials_or_image():
    from kcore.unitv2_lifecycle import diagnostic_status
    raw={'mode':'ON_DEMAND','state':'STOPPED','stop_confirmed':True,'starts':2,'key':KEY,'lease':'private','jpeg':jpeg()}
    safe=diagnostic_status(raw)
    assert safe=={'mode':'ON_DEMAND','state':'STOPPED','stop_confirmed':True,'starts':2}


def test_device_code_remains_python38_compatible():
    for path in (ROOT/'unitv2').glob('*.py'):ast.parse(path.read_text(),feature_version=(3,8))


def test_sensor_to_perception_owns_one_real_producer_for_two_frames(service,tmp_path):
    from kcore.perception import PerceptionController
    from kcore.local_faces import Face
    from kcore.schema import ensure_schema
    from kcore.storage import KadencePaths
    from types import SimpleNamespace
    server,_=service
    async def case():
        paths=KadencePaths.for_root(tmp_path);ensure_schema(paths)
        camera=CameraManager(None,config=CameraConfig(policy='EVENT_ONLY',source='unitv2-camera',address='127.0.0.1',perception_enabled=True))
        camera.unitv2=UnitV2Owner(lambda *a:None,key_loader=lambda:KEY,client_factory=lambda a,k:Client(a,k,port=server.server_port))
        await camera.unitv2.refresh('127.0.0.1');camera.unitv2.verified=True
        count=[]
        def analyze(png):
            count.append(png)
            return (Face((0,0,.5,.5),tuple(float(i==0) for i in range(128)),1),)
        pc=PerceptionController(camera,paths,lambda *a:None,None,lambda:False,faces=SimpleNamespace(health='ready',analyze=analyze))
        await pc.start()
        from kcore.sensors import GestureStatus
        await pc.sample(pc.sampler.sample(None,GestureStatus('ready',1,0,0,0,0)))
        await pc.sample(pc.sampler.sample(None,GestureStatus('ready',2,0,1,0,1)))
        await pc.task
        status=await camera.unitv2.refresh('127.0.0.1')
        assert len(count)==2 and status['starts']==1 and status['stops']==1 and status['stop_confirmed']
        assert pc.health=='ready' and pc._completed_bursts==1
        await pc.close();await camera.close()
    asyncio.run(case())


def test_reversible_install_rejects_unknown_files_before_writing(tmp_path,monkeypatch):
    root=tmp_path/'device';source=tmp_path/'package';root.mkdir();source.mkdir();(root/'bin').mkdir()
    original=b'original factory entry\r\n';binary=b'factory-camera'
    (root/'server_core.py').write_bytes(original);(root/'bin/camera_stream').write_bytes(binary)
    code=b'def main(): pass\n';(source/'kadence_unitv2.py').write_bytes(code)
    (source/'manifest.json').write_text(json.dumps({'kadence_unitv2.py':hashlib.sha256(code).hexdigest()}))
    (source/'kadence-camera.key').write_text(KEY)
    monkeypatch.setattr(installer,'CAMERA_SHA256',hashlib.sha256(binary).hexdigest())
    with pytest.raises(RuntimeError,match='Factory service has changed'):installer.install(root,source)
    assert (root/'server_core.py').read_bytes()==original and not (root/'server_core.kadence-original.py').exists()
    monkeypatch.setattr(installer,'FACTORY_SHA256',hashlib.sha256(original).hexdigest())
    assert installer.install(root,source)['result']=='installed'
    assert (root/'server_core.py').read_bytes()==installer.SHIM
    assert (root/'server_core.kadence-original.py').read_bytes()==original
    assert installer.install(root,source)['result']=='installed'  # Update preserves first backup.
    assert installer.install(root,source,restore=True)['result']=='restored'
    assert (root/'server_core.py').read_bytes()==original
    (root/'server_core.kadence-original.py').chmod(0o644)
