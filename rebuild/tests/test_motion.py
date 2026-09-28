import asyncio
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from kcore.motion import HomeStore,Motion


def app_at(root):
    moves=[]
    async def send(yaw,pitch,**kwargs):moves.append((yaw,pitch));return NS(payload={'ok':True,'executed':True,'torque_released':True})
    app=NS(_body=NS(connected=True,send_body_pose=send),_voice_task=None,perception=None,
           tracking=NS(stop=AsyncMock()),emit=lambda *a:None)
    app._last_device_status={"firmware":"0.21.6"};app._last_device_status_at=time.monotonic()
    app.motion=Motion(app,HomeStore(root))
    return app,moves


def test_home_persists_and_tracking_uses_same_coordinates(tmp_path):
    async def case():
        app,moves=app_at(tmp_path)
        await app.motion.command('motion_set_home',{'yaw':120,'pitch':410})
        assert HomeStore(tmp_path).home==(120,410)
        from kcore.object_tracking import ObjectTracking
        tracker=ObjectTracking.__new__(ObjectTracking);tracker.app=app
        assert tracker.home==(120,410)
        await app.motion.command('motion_home',{})
        assert moves==[(120,410),(120,410)]
        assert 'zero' not in app.motion.store.path.read_text()
    asyncio.run(case())


def test_failed_ack_never_overwrites_home(tmp_path):
    async def case():
        app,_=app_at(tmp_path);app.motion.store.save((10,300))
        app._body.send_body_pose=AsyncMock(return_value=NS(payload={'ok':True,'executed':True,'torque_released':False}))
        with pytest.raises(RuntimeError):await app.motion.command('motion_set_home',{'yaw':20,'pitch':350})
        assert HomeStore(tmp_path).home==(10,300)
        with pytest.raises(ValueError):await app.motion.command('motion_set_home',{'yaw':999,'pitch':350})
    asyncio.run(case())


def test_cancelled_set_home_drains_existing_move_and_does_not_save(tmp_path):
    async def case():
        app,_=app_at(tmp_path);entered=asyncio.Event();release=asyncio.Event()
        async def send(*a,**kw):entered.set();await release.wait();return NS(payload={'ok':True,'executed':True,'torque_released':True})
        app._body.send_body_pose=send
        task=asyncio.create_task(app.motion.command('motion_set_home',{'yaw':20,'pitch':350}))
        await entered.wait();task.cancel();await asyncio.sleep(0)
        assert not task.done();release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert not app.motion.store.saved
    asyncio.run(case())


def test_stop_supersedes_a_home_request_waiting_for_perception(tmp_path):
    async def case():
        app,moves=app_at(tmp_path);app.motion.store.save((0,300))
        entered=asyncio.Event();release=asyncio.Event()
        async def pause():entered.set();await release.wait()
        app.perception=NS(interrupt=pause)
        task=asyncio.create_task(app.motion.command('motion_home',{}))
        await entered.wait();await app.motion.command('motion_stop',{});release.set()
        with pytest.raises(RuntimeError,match='superseded'):await task
        assert moves==[]
    asyncio.run(case())
