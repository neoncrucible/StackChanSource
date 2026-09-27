"""Real process/HTTP tracking, stale-box rejection, ownership and motor draining."""
import asyncio
import base64
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import uuid

import pytest
from PIL import Image
import numpy as np

from kcore.camera_manager import CameraConfig,CameraManager
from kcore.object_tracking import ObjectTracking
from kcore.unitv2_lifecycle import Client,UnitV2Owner,LifecycleError
from kcore.tracking_target import target_box,relocate
from kcore.camera_voice import camera_plan

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'unitv2'))
import kadence_unitv2 as service
import kadence_tracking as tracking

KEY='ef'*32


@pytest.fixture
def tracker_service(tmp_path):
    image=Image.fromarray(np.random.default_rng(123).integers(0,256,(240,320,3),dtype=np.uint8))
    output=io.BytesIO();image.save(output,'JPEG',quality=92)
    script=tmp_path/'tracker.py'
    script.write_text('JPEG='+repr(base64.b64encode(output.getvalue()).decode())+'\n'+r'''
import sys,json,time,threading,queue
from pathlib import Path
q=queue.Queue()
def reader():
 for line in sys.stdin:
  if not line.startswith('_'):q.put(json.loads(line))
threading.Thread(target=reader,daemon=True).start()
roi=None
while True:
 while not q.empty():
  roi=q.get()
  print(json.dumps({'running':'Target Tracker','msg':'ROI updated.'}),flush=True)
 scene=Path('scene').read_text()
 if scene=='silent':time.sleep(.03);continue
 if roi and scene!='lost':
  box={k:roi[k] for k in ('x','y','w','h')}
  print(json.dumps(dict(running='Target Tracker',**box)),flush=True)
 print(json.dumps({'img':JPEG}),flush=True)
 time.sleep(.025)
''')
    (tmp_path/'scene').write_text('visible')
    producer=service.Producer([sys.executable,str(script)],str(tmp_path))
    bridge=tracking.TrackingBridge(producer,service.CameraError,tmp_path,command=[sys.executable,str(script)])
    server=service.Server(('127.0.0.1',0),service.CameraService(producer,KEY))
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    watcher=threading.Thread(target=producer.watchdog,daemon=True);watcher.start()
    client=Client('127.0.0.1',KEY,port=server.server_port)
    yield producer,bridge,client,tmp_path
    producer.close();server.shutdown();server.server_close();thread.join(2);watcher.join(2)


def test_native_box_is_cleared_on_each_lost_frame_and_new_lease(tracker_service):
    p,b,c,root=tracker_service;lease=uuid.uuid4().hex
    c.call('track_start',lease)
    first=c.call('track_frame',lease);assert first['box'] is None
    selected=c.call('track_select',lease,roi=[300,180,80,100])
    result=c.call('track_frame',lease)
    assert result['box']==[300,180,80,100] and result['target_epoch']==selected['target_epoch']
    (root/'scene').write_text('lost')
    for _ in range(5): result=c.call('track_frame',lease)
    assert result['box'] is None and result['sequence']>first['sequence']
    assert c.call('stop',lease)['stop_confirmed']
    with pytest.raises(LifecycleError):c.call('track_start',lease)
    lease=uuid.uuid4().hex;c.call('track_start',lease)
    assert c.call('track_frame',lease)['box'] is None


@pytest.mark.parametrize('roi',[[True,0,20,20],[-1,0,20,20],[630,0,40,20],[0,0,0,20],[0,0,20,500],{'x':1}])
def test_native_rejects_invalid_regions_without_initialising(tracker_service,roi):
    p,b,c,root=tracker_service;lease=uuid.uuid4().hex;c.call('track_start',lease)
    with pytest.raises(LifecycleError):c.call('track_select',lease,roi=roi)
    assert not b.selected


def make_app(client):
    events=[];moves=[]
    async def pose(yaw,pitch,**kw):
        moves.append((yaw,pitch));await asyncio.sleep(.01)
        return SimpleNamespace(payload={'ok':True,'executed':True,'torque_released':True})
    camera=CameraManager(None,config=CameraConfig(source='unitv2-camera',address=client.address),emit=lambda n,d:events.append((n,d)) if n!='tracking_preview' else None)
    camera.unitv2=UnitV2Owner(camera.emit,key_loader=lambda:KEY,client_factory=lambda *a:client)
    camera.unitv2.verified=True
    app=SimpleNamespace(camera=camera,emit=camera.emit,perception=None,_voice_task=None,
        settings=SimpleNamespace(providers=None),_body=SimpleNamespace(connected=True,send_body_pose=pose),
        _last_device_status={'firmware':'0.21.6'},_last_device_status_at=time.monotonic())
    app.tracking=ObjectTracking(app)
    return app,events,moves


def test_controller_owns_one_process_tracks_and_privacy_stops(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        await t.preview()
        sequence=t.frames[-1][0]
        await t.select([650,350,180,250],sequence)
        await asyncio.sleep(.4)
        assert t.state=='TRACKING' and not moves and p.starts==1
        with pytest.raises(RuntimeError,match='busy'):await app.camera.acquire()
        app.camera.configure(replace(app.camera.config,privacy=True))
        task=t.task
        if task:
            with pytest.raises(asyncio.CancelledError):await task
        assert p.status()['stop_confirmed'] and app.camera._active is None and not t.frames
        await t.stop();await app.camera.close()
    asyncio.run(run())


def test_head_steps_require_arming_and_stop_on_loss_or_voice(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        with pytest.raises(ValueError,match='mounted'):await t.arm({})
        await t.arm({'mounted':True})
        assert t.armed and moves==[(0,300)]
        await t.preview();await t.select([650,350,180,250],t.frames[-1][0])
        await asyncio.sleep(1)
        assert len(moves)>1
        assert all(abs(b[0]-a[0])<=20 and abs(b[1]-a[1])<=20 for a,b in zip(moves,moves[1:]))
        app._voice_task=asyncio.create_task(asyncio.sleep(2));count=len(moves)
        await asyncio.sleep(.25);assert len(moves)==count
        app._voice_task.cancel()
        with pytest.raises(asyncio.CancelledError):await app._voice_task
        (root/'scene').write_text('lost')
        await asyncio.sleep(2)
        assert t.state=='LOST'
        count=len(moves);await asyncio.sleep(.25);assert len(moves)==count
        await t.stop(disarm=True);assert not t.armed and p.status()['stop_confirmed']
        await app.camera.close()
    asyncio.run(run())


def test_cancelling_move_waits_for_real_ack_and_never_queues_another(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        entered=asyncio.Event();release=asyncio.Event()
        async def slow(*args,**kw):
            entered.set();await release.wait();return SimpleNamespace(payload={'ok':True,'executed':True,'torque_released':True})
        app._body.send_body_pose=slow
        action=asyncio.create_task(t.arm({'mounted':True}))
        await entered.wait()
        stop=asyncio.create_task(t.stop(disarm=True));await asyncio.sleep(.05)
        assert not stop.done() and not action.done()
        release.set();await stop
        with pytest.raises(asyncio.CancelledError):await action
        assert not t.armed and t.move is None
        await app.camera.close()
    asyncio.run(run())


def test_tracking_lease_expires_without_host(tracker_service):
    p,b,c,root=tracker_service;lease=uuid.uuid4().hex;c.call('track_start',lease)
    with p.lock:p.expires=p.clock()-1
    p.watchdog_once()
    assert p.status()['stop_confirmed'] and not b.selected


def test_voice_target_schema_and_negations():
    assert camera_plan('Kadence, follow this pen.')=={'tool':'tracking_control','arguments':{'action':'follow','target':'this pen'}}
    assert camera_plan('stop tracking')['arguments']['action']=='stop'
    for phrase in ('do not follow this pen','what happens if I say follow this pen','the label says track this pen'):
        assert camera_plan(phrase) is None
    assert target_box('{"found":true,"box":[100,200,500,600],"confidence":0.9}')==[200,100,400,400]
    for raw in ('{"found":false}','{"found":true,"box":[0,0,999,999],"confidence":0.5}','{"found":true,"box":[true,0,500,500],"confidence":0.9}'):
        with pytest.raises(RuntimeError):target_box(raw)


def test_selection_aligns_current_image_and_rejects_changed_object():
    def png(array):
        output=io.BytesIO();Image.fromarray(array).save(output,'PNG');return output.getvalue()
    a=np.random.default_rng(32).integers(0,256,(240,320,3),dtype=np.uint8)
    before=png(a);b=a.copy();b[100:148,160:224]=a[48:96,64:128];b[48:96,64:128]=0
    assert relocate(before,png(b),[200,200,200,200])==[320,200,128,96]
    with pytest.raises(RuntimeError):relocate(before,png(np.zeros_like(a)),[200,200,200,200])


def test_stop_during_semantic_selection_cancels_provider_and_camera(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def locate(*args):
            entered.set()
            try:await asyncio.sleep(99)
            finally:cancelled.set()
        t.locator=locate
        action=asyncio.create_task(t.select(target='pen'));await entered.wait()
        await t.stop(disarm=True)
        with pytest.raises(asyncio.CancelledError):await action
        assert cancelled.is_set() and not t.active and p.status()['stop_confirmed'] and not moves
        await app.camera.close()
    asyncio.run(run())


def test_stop_supersedes_preview_before_camera_start(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        entered=asyncio.Event();release=asyncio.Event()
        async def interrupt(): entered.set();await release.wait()
        app.perception=SimpleNamespace(interrupt=interrupt)
        task=asyncio.create_task(t.preview());await entered.wait()
        await t.stop();release.set()
        with pytest.raises(RuntimeError,match='superseded'):await task
        assert p.starts==0 and not t.active
        await app.camera.close()
    asyncio.run(run())


def test_voice_tracking_dispatch_requires_explicit_request_or_confirmation(tmp_path):
    from kcore.services import LocalServices
    from kcore.companion import Companion
    class NoPlanner:
        async def generate(self,*args,**kwargs):raise AssertionError('Explicit tracking must be local')
    async def run():
        services=LocalServices(tmp_path);await services.start()
        calls=[]
        async def tracking(args): calls.append(args);return {'spoken':'Selected the test target.'}
        services.tracking_handler=tracking
        companion=Companion(services.tools)
        assert await companion.respond('Kadence, follow this pen',NoPlanner())=='Selected the test target.'
        assert calls==[{'action':'follow','target':'this pen'}]
        await companion.respond('Stop tracking',NoPlanner())
        assert calls[-1]=={'action':'stop'}
        denied=await services.tools.execute('tracking_control',{'action':'follow','target':'pen'})
        assert not denied['ok'] and len(calls)==2
        status=await services.command('local_tool',{'name':'tracking_status'})
        assert status['ok'] and status['data']['spoken']=='Selected the test target.'
        assert calls[-1]=={}
        with pytest.raises(ValueError,match='Unsupported desktop tool'):
            await services.command('local_tool',{'name':'tracking_control','arguments':{'action':'follow','target':'pen'}})
        await services.close()
    asyncio.run(run())


def test_preview_drag_uses_image_coordinates_inside_letterbox():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QPoint,Qt
    from PySide6.QtTest import QTest
    from kcore.tracking_ui import TargetPreview
    app=QApplication.instance() or QApplication([])
    widget=TargetPreview();widget.resize(800,300)
    widget.pixmap=QPixmap(320,240);widget.pixmap.fill(Qt.black);widget.sequence=41
    widget.show();app.processEvents()
    assert widget.image_rect().x()==200
    results=[];widget.selected.connect(results.append)
    QTest.mousePress(widget,Qt.LeftButton,pos=QPoint(240,30))
    QTest.mouseMove(widget,QPoint(440,180))
    QTest.mouseRelease(widget,Qt.LeftButton,pos=QPoint(440,180))
    assert results==[{'sequence':41,'region':[100,100,500,500]}]
    widget.frame({});assert widget.sequence is None and widget.pixmap.isNull()
    widget.close()


def test_tracking_diagnostics_exclude_images_labels_and_messages():
    from kcore.object_tracking import diagnostic_status
    value=diagnostic_status({'state':'TRACKING','armed':True,'active':True,'head_yaw':2.0,'head_pitch':30.0,
                            'message':'private object','png':'private pixels','target':'private label'})
    assert value=={'state':'TRACKING','armed':True,'active':True,'head_yaw':2.0,'head_pitch':30.0}
