"""Natural target selection and continuity through speech, loss and restart."""
import asyncio
import base64
import io
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import numpy as np
from PIL import Image

from kcore.tracking_target import local_target, relocate
from kcore.motion import HomeStore, Motion
from test_object_tracking import tracker_service, make_app


def jpeg(scene):
    output=io.BytesIO();Image.fromarray(scene).save(output,'JPEG',quality=95)
    return output.getvalue()


def test_single_colour_needs_no_cloud_and_duplicate_colour_is_ambiguous():
    scene=np.zeros((240,320,3),np.uint8)+20
    scene[80:130,120:170]=(230,15,15)
    image=jpeg(scene)
    region=local_target(image,'something red')
    assert region is not None
    x,y,w,h=relocate(image,image,region)
    assert x<=240 and y<=160 and x+w>=340 and y+h>=260
    assert local_target(image,'the red mug') is None  # colour is not object identity
    scene[80:130,200:250]=(230,15,15)
    assert local_target(jpeg(scene),'the red object') is None


def test_track_that_uses_one_moving_object_but_rejects_global_motion():
    random=np.random.default_rng(8)
    scene=random.integers(40,100,(240,320,3),dtype=np.uint8)
    before=scene.copy();before[80:120,125:155]=(220,180,50)
    after=scene.copy();after[80:120,140:170]=(220,180,50)
    region=local_target(jpeg(after),'that',jpeg(before))
    assert region is not None
    assert local_target(jpeg(after),'a pen',jpeg(before)) is None
    assert local_target(jpeg(after),'that',jpeg(after)) is None
    assert local_target(jpeg(np.clip(after.astype(int)+80,0,255).astype('uint8')),'that',jpeg(after)) is None
    other_before=before.copy();other_after=after.copy()
    other_before[160:200,40:70]=(220,180,50);other_after[160:200,55:85]=(220,180,50)
    assert local_target(jpeg(other_after),'that',jpeg(other_before)) is None


def test_native_jpeg_preview_and_camera_continue_during_speech(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        previews=[]
        t.emit=lambda name,data:previews.append(data) if name=='tracking_preview' and data else None
        await t.preview();await t.select([650,350,180,250],t.frames[-1][0])
        starts=p.starts;sequence=t.last_sequence
        app._voice_task=asyncio.create_task(asyncio.sleep(.4))
        await app._voice_task
        assert t.state=='TRACKING' and t.last_sequence>sequence+2 and p.starts==starts
        assert previews and all(base64.b64decode(data['jpeg']).startswith(b'\xff\xd8') for data in previews)
        assert not moves
        await t.stop();await app.camera.close()
    asyncio.run(run())


def test_first_track_that_collects_motion_and_selects_without_cloud(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        scene=np.random.default_rng(8).integers(40,100,(240,320,3),dtype=np.uint8)
        before=scene.copy();before[80:120,125:155]=(220,180,50)
        after=scene.copy();after[80:120,140:170]=(220,180,50)
        (root/'image').write_text(base64.b64encode(jpeg(before)).decode())
        t.locator=AsyncMock(side_effect=AssertionError('Cloud should not be needed'))
        await t.preview()
        async def present():
            await asyncio.sleep(.08)
            temporary=root/'image.new'
            temporary.write_text(base64.b64encode(jpeg(after)).decode());temporary.replace(root/'image')
        changing=asyncio.create_task(present())
        result=await t.select(target='that')
        await changing
        assert t.state=='TRACKING' and 'tracking' in result['spoken']
        t.locator.assert_not_called()
        await t.stop();await app.camera.close()
    asyncio.run(run())


def test_brief_loss_resumes_only_matching_appearance(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        await t.preview();await t.select([650,350,180,250],t.frames[-1][0])
        await asyncio.sleep(.1)
        (root/'scene').write_text('lost');await asyncio.sleep(1.8)
        assert t.state=='LOST' and not moves
        (root/'scene').write_text('visible');await asyncio.sleep(.4)
        assert t.state=='TRACKING' and not moves
        t.state='LOST';t.lost_at=time.monotonic();t._last_good=(jpeg(np.zeros((240,320,3),np.uint8)),[400,150,110,120])
        await asyncio.sleep(.2)
        assert t.state=='LOST'
        await t.stop();await app.camera.close()
    asyncio.run(run())


def test_saved_head_setup_automatically_positions_before_selecting_and_stop_cancels_queue(tracker_service):
    async def run():
        p,b,c,root=tracker_service;app,events,moves=make_app(c);t=app.tracking
        app.services=NS(paths=NS(root=root))
        app.motion=Motion(app,HomeStore(root));app.motion.store.save((0,300))
        await t.arm({'mounted':True,'yaw_sign':-1,'pitch_sign':1})
        assert t.saved_head_setup()=={'mounted':True,'yaw_sign':-1,'pitch_sign':1}
        await t.stop(disarm=True)
        t.locator=AsyncMock(return_value=[650,350,180,250])
        app._voice_task=asyncio.create_task(asyncio.sleep(.3));count=len(moves)
        await t.select(target='this pen')
        queued=t.operation
        await asyncio.sleep(.05)
        assert len(moves)==count and not t.active
        await queued
        assert t.active and t.armed and t.signs==(-1,1) and len(moves)>count
        await t.stop(disarm=True)
        app._voice_task=asyncio.create_task(asyncio.sleep(.3));count=len(moves)
        await t.select(target='this pen');await t.stop(disarm=True)
        await app._voice_task;await asyncio.sleep(.1)
        assert not t.active and not t.armed and len(moves)==count
        # Changing the common home invalidates the previous mounting setup.
        app.motion.store.save((20,300));assert t.saved_head_setup() is None
        await app.camera.close()
    asyncio.run(run())
