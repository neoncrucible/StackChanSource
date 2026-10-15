"""Owner-reported journeys: language -> real camera lease -> evidence -> action."""
import asyncio
import base64
from dataclasses import replace
import io
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from kcore.camera_manager import CameraConfig
from kcore.camera_voice import camera_plan
from kcore.companion import Companion
from kcore.desktop_worker import DesktopController
from kcore.motion import HomeStore, Motion
from kcore.presence_motion import PresenceMotion
from kcore.tracking_evidence import signature, agrees
from test_object_tracking import tracker_service, make_app


@pytest.mark.parametrize('phrase',[
    'What do I have in my hand?', "What have I got in my hand?", "What's in my hand?",
    'Can you tell me what I have in my hand?', 'What colour is it?', 'Is it still there?',
    'Where did the bottle go?', 'Has the bottle moved?',
])
def test_present_object_questions_require_a_fresh_look(phrase):
    assert camera_plan(phrase)['tool']=='desk_look'


@pytest.mark.parametrize('phrase',[
    'Tell me if it gets moved', 'Let me know when the bottle moves',
    'Can you tell me if that disappears?', 'Watch the bottle', 'Monitor that for movement',
])
def test_monitoring_is_a_real_watch_operation(phrase):
    plan=camera_plan(phrase)
    assert plan['tool']=='tracking_control' and plan['arguments']['action']=='watch'


def test_defaults_are_once_only_preserve_privacy_and_back_up_the_previous_choices(tmp_path):
    old=CameraConfig(privacy=True,source='robot-camera')
    old.save(tmp_path)
    result=CameraConfig.companion_defaults(tmp_path)
    assert result.privacy and result.source=='robot-camera'
    assert result.greetings and result.perception_enabled and result.policy=='AWARE'
    assert (tmp_path/'camera-settings.pre-0.6.1.json').exists()
    chosen=replace(result,policy='OFF',perception_enabled=False,greetings=False)
    chosen.save(tmp_path)
    assert CameraConfig.companion_defaults(tmp_path)==chosen


def test_semantic_vision_fallback_accepts_new_wording_without_loosening_privacy_intent(tmp_path):
    import json
    class Planner:
        async def stream_reply(self,text):
            yield json.dumps({'tool':'desk_look','arguments':{'question':'model wording'}})
    async def run():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        try:
            look=worker.services.look_handler=AsyncMock(return_value={'spoken':'A blue bottle, Boss.'})
            companion=Companion(worker.services.tools)
            for question in ("Any idea what I've got here?", "Can you make out what I'm holding?", 'Could you inspect this for me?'):
                assert await companion.respond(question,Planner())=='A blue bottle, Boss.'
                look.assert_awaited_with(question)
            count=look.await_count
            for question in ('Tell me a joke', 'Describe the French Revolution', "Don't look at this", 'Explain what this phrase means'):
                await companion.respond(question,Planner())
            assert look.await_count==count
        finally:await worker.close()
    asyncio.run(run())


def test_grounding_guard_keeps_ordinary_banter_and_rejects_fake_action_claims(tmp_path):
    import json
    class Reply:
        def __init__(self,text):self.text=text
        async def stream_reply(self,prompt):yield json.dumps({'reply':self.text})
    async def run():
        worker=DesktopController(lambda *a:None,directory=tmp_path);await worker.start()
        try:
            companion=Companion(worker.services.tools)
            text='I can see your point, Boss. Annoyingly, you are right.'
            assert await companion.respond('That makes more sense.',Reply(text))==text
            answer=await companion.respond('What about the bottle?',Reply("I'm tracking the bottle, darling."))
            assert "haven't verified" in answer and 'darling' not in answer
        finally:await worker.close()
    asyncio.run(run())


def test_voice_follow_reuses_legacy_shared_home_and_proves_target_before_promise(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        app.services=NS(paths=NS(root=root));app.motion=Motion(app,HomeStore(root));app.motion.store.save((0,300))
        t.locator=AsyncMock(return_value=[650,350,180,250])
        release=asyncio.Event();app._voice_task=asyncio.create_task(release.wait())
        try:
            result=await t.select(target='the bottle')
            assert result['target_confirmed'] and result['head_pending'] and not moves
            assert t.last_box and t.active and not t.saved_head_setup()
            release.set();await app._voice_task
            async with asyncio.timeout(2):
                while len(moves)<2:await asyncio.sleep(.02)
            assert t.armed and moves[0]==(0,300)
            assert all(abs(b[0]-a[0])<=20 for a,b in zip(moves,moves[1:]))
        finally:
            release.set();await app._voice_task;await t.stop(disarm=True);await app.camera.close()
    asyncio.run(run())


def test_follow_establishes_accepted_legacy_home_without_an_arm_toggle(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        app.services=NS(paths=NS(root=root));app.motion=Motion(app,HomeStore(root))
        t.locator=AsyncMock(return_value=[650,350,180,250])
        try:
            assert not app.motion.store.saved
            result=await t.select(target='the bottle')
            assert result['target_confirmed'] and result['head_following']
            assert moves[0]==(0,300) and app.motion.store.saved and t.saved_head_setup()
        finally:await t.stop(disarm=True);await app.camera.close()
    asyncio.run(run())


def test_failed_home_ack_never_saves_calibration_or_claims_following(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        app.services=NS(paths=NS(root=root));app.motion=Motion(app,HomeStore(root))
        app._body.send_body_pose=AsyncMock(return_value=NS(payload={'ok':False,'executed':False,'torque_released':False}))
        try:
            with pytest.raises(RuntimeError,match='not confirmed'):await t.select(target='the bottle')
            assert not app.motion.store.saved and not t.armed and not t.active
        finally:await t.stop();await app.camera.close()
    asyncio.run(run())


def test_roi_ack_without_a_visible_target_never_says_tracking(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        (root/'scene').write_text('lost');t.locator=AsyncMock(return_value=[650,350,180,250])
        try:
            with pytest.raises(RuntimeError,match="couldn't keep a lock"):
                await t.select(target='the bottle')
            assert t.state=='SELECTING' and not moves
            assert not any('I am tracking' in d.get('message','') for n,d in events)
        finally:await t.stop();await app.camera.close()
    asyncio.run(run())


def test_watch_uses_existing_target_and_alerts_once_on_sustained_loss(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        t.locator=AsyncMock(return_value=[650,350,180,250])
        try:
            await t.select(target='the bottle',follow=False)
            starts=p.starts
            answer=await t.watch('it')
            assert answer['watching'] and not t.armed and p.starts==starts
            (root/'scene').write_text('lost')
            async with asyncio.timeout(4):
                while t._notice is None:await asyncio.sleep(.03)
            message=t.take_notice()
            assert 'lost sight of the bottle' in message and 'covered' in message
            assert t.take_notice() is None and not moves
            assert len([n for n,d in events if n=='tracking_notice'])==1
        finally:await t.stop();await app.camera.close()
    asyncio.run(run())


def test_fresh_visual_question_borrows_tracking_lease_without_losing_target(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        try:
            await t.preview();await t.select([650,350,180,250],t.frames[-1][0])
            starts=p.starts;sequence=t.last_sequence;epoch=t.expected_epoch
            frame=await t.current_frame()
            assert frame.source=='unitv2-camera' and int(frame.frame_id)>sequence
            assert frame.png.startswith(b'\x89PNG') and p.starts==starts
            assert t.state=='TRACKING' and t.expected_epoch==epoch
        finally:await t.stop();await app.camera.close()
    asyncio.run(run())


def bottle_image(hidden=False):
    image=Image.new('RGB',(320,240),(130,120,100));draw=ImageDraw.Draw(image)
    if not hidden:
        draw.rectangle((125,65,175,175),fill=(15,70,220))
        draw.rectangle((140,50,160,65),fill=(25,35,90))
        draw.text((130,100),'WATER',fill='white')
    output=io.BytesIO();image.save(output,'JPEG');return output.getvalue()


def test_frozen_native_box_cannot_hide_a_disappearing_blue_bottle():
    box=[250,100,100,250]
    reference=signature(bottle_image(),box)
    assert agrees(reference,bottle_image(),box)
    assert not agrees(reference,bottle_image(hidden=True),box)


def test_hidden_bottle_alerts_even_when_native_tracker_keeps_reporting_old_box(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        (root/'image').write_text(base64.b64encode(bottle_image()).decode())
        t.locator=AsyncMock(return_value=[390,208,156,521])
        try:
            await t.select(target='the blue bottle',follow=False)
            await t.watch('it')
            temporary=root/'image.new';temporary.write_text(base64.b64encode(bottle_image(True)).decode());temporary.replace(root/'image')
            async with asyncio.timeout(4):
                while t._notice is None:await asyncio.sleep(.03)
            assert t._observation['box'] is not None  # Simulate tracker drift onto background.
            assert 'lost sight' in t.take_notice() and not moves
        finally:await t.stop();await app.camera.close()
    asyncio.run(run())


def test_startup_arrival_waits_for_camera_readiness_instead_of_disappearing(tmp_path):
    from test_autonomous_perception import controller, sample, vector
    async def run():
        e=await controller(tmp_path,source='unitv2-camera',greetings=True)
        try:
            await e.pc.db('enroll',name='Boss',vectors=[vector()]*3)
            await sample(e,0,1);await sample(e,1,2);await sample(e,2.1,3)
            assert e.pc.pending and e.pc.pending['trigger']=='arrival' and not e.pc.task
            e.camera.unitv2.verified=True;e.now[0]=3
            await e.pc.tick()
            assert e.pc.task is not None
            await e.pc.task
            assert e.pc._completed_bursts==1 and len(e.delivered)==1
        finally:await e.pc.close();await e.camera.close()
    asyncio.run(run())


def test_idle_presence_uses_one_bounded_motion_lane_and_yields_to_voice(tmp_path):
    async def run():
        now=[40.0];moves=[]
        app=NS(_stop=asyncio.Event(),_voice_task=None,_last_device_status={'firmware':'0.21.6'},_last_device_status_at=40,
            _body=NS(connected=True),camera=NS(config=CameraConfig(policy='AWARE',perception_enabled=True),_active=None),
            perception=NS(gate=lambda:'ready',occupancy=NS(state='OCCUPIED'),task=None),
            tracking=NS(active=False,operation=None),emit=lambda *args:None)
        async def send(yaw,pitch,**kwargs):
            moves.append((yaw,pitch));return NS(payload={'ok':True,'executed':True,'torque_released':True})
        app._body.send_body_pose=send;app.motion=Motion(app,HomeStore(tmp_path));app.motion.store.save((0,300))
        presence=PresenceMotion(app,clock=lambda:now[0]);presence.next_at=0
        presence.tick();await presence.task
        assert moves==[(-35,310)]
        now[0]=90;app._last_device_status_at=90
        app._voice_task=asyncio.create_task(asyncio.sleep(.02));presence.tick()
        await app._voice_task
        assert moves==[(-35,310)]
        app.camera.config=replace(app.camera.config,privacy=True);presence.next_at=0;presence.tick()
        assert moves==[(-35,310)]
        await presence.pause()
        # An older install first establishes Home, then makes its first glance;
        # it must not spend two further idle intervals commanding Home again.
        app.camera.config=replace(app.camera.config,privacy=False)
        app.motion.store.saved=False;presence=PresenceMotion(app,clock=lambda:now[0]);presence.next_at=0
        presence.tick();await presence.task
        assert moves[-1]==(0,300) and presence.next_at==95
        now[0]=95;app._last_device_status_at=95;presence.tick();await presence.task
        assert moves[-1]==(-35,310)
        await presence.pause()
    asyncio.run(run())
