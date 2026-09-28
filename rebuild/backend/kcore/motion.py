"""One persisted home and one acknowledged motor lane; no servo-zero writes."""
from __future__ import annotations
import asyncio
import contextlib
import json
import time
from pathlib import Path


def pose(value):
    if not isinstance(value, dict) or set(value)-{'yaw','pitch'}: raise ValueError('Invalid pose fields.')
    yaw,pitch=value.get('yaw'),value.get('pitch')
    if type(yaw) is not int or not -320<=yaw<=320 or type(pitch) is not int or not 30<=pitch<=870:
        raise ValueError('Pose must be yaw -32..32 and pitch 3..87 degrees.')
    return yaw,pitch


class HomeStore:
    def __init__(self, directory):
        self.path=Path(directory)/'motion-home.json'
        self.home=(0,300);self.saved=False
        try:
            self.home=pose(json.loads(self.path.read_text()));self.saved=True
        except (OSError,ValueError,TypeError): pass

    def save(self, target):
        target=pose(dict(zip(('yaw','pitch'),target)))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(zip(('yaw','pitch'),target))))
        tmp.replace(self.path)
        self.home=target;self.saved=True


class Motion:
    def __init__(self, app, home):
        self.app,self.store=app,home
        self.task=None;self.generation=0;self.last_pose=None

    def status(self, message=''):
        value={'home':dict(zip(('yaw','pitch'),self.store.home)),'saved':self.store.saved,
               'last_confirmed':dict(zip(('yaw','pitch'),self.last_pose)) if self.last_pose else None,
               'moving':bool(self.task and not self.task.done()),'message':message}
        self.app.emit('motion_status',value)
        return value

    async def stop(self):
        self.generation+=1
        task=self.task
        # A firmware-issued move must settle before any subsequent physical work.
        while task and not task.done():
            try: await asyncio.shield(task)
            except asyncio.CancelledError: continue
            except Exception: break
        if task:
            with contextlib.suppress(Exception,asyncio.CancelledError): task.result()

    async def move(self, target, *, guard=None):
        target=pose(dict(zip(('yaw','pitch'),target)))
        if self.task and not self.task.done(): raise RuntimeError('A head movement is already settling.')
        body=self.app._body
        if not body or not body.connected: raise RuntimeError('Connect the robot before moving its head.')
        token=self.generation
        async def send():
            if token!=self.generation: raise RuntimeError('Head movement was cancelled before dispatch.')
            if guard: guard()
            voice=getattr(self.app,'_voice_task',None)
            if voice and not voice.done(): raise RuntimeError('Wait for voice to finish before moving the head.')
            ack=await body.send_body_pose(*target,timeout=10)
            if any(ack.payload.get(k) is not True for k in ('ok','executed','torque_released')):
                self.last_pose=None
                raise RuntimeError('Movement or torque release was not confirmed.')
            self.last_pose=target
        task=self.task=asyncio.create_task(send(),name='kadence-motion')
        self.status('Moving; waiting for position and torque confirmation.')
        try: await asyncio.shield(task)
        finally:
            while not task.done():
                try: await asyncio.shield(task)
                except asyncio.CancelledError: continue
                except Exception: break
            if self.task is task:self.task=None
            self.status('Head movement settled.')

    async def command(self, action, args):
        if action=='motion_status':return self.status()
        self.generation+=1
        generation=self.generation
        await self.app.tracking.stop(disarm=True)
        if action=='motion_stop':
            await self.stop();return self.status('Further movement stopped; torque released after any issued move.')
        if self.task and not self.task.done():raise RuntimeError('Wait for the current movement to settle.')
        if self.app.perception:await self.app.perception.interrupt()
        if generation!=self.generation:raise RuntimeError('Head action was superseded by Stop.')
        if self.app._last_device_status.get('firmware')!='0.21.6' or time.monotonic()-self.app._last_device_status_at>5:
            raise RuntimeError('Motion requires connected firmware 0.21.6 and a fresh device status.')
        if action=='motion_home' and not self.store.saved:raise RuntimeError('Set the shared home before returning Home.')
        target=self.store.home if action=='motion_home' else pose(args)
        await self.move(target)
        if action=='motion_set_home':
            if generation!=self.generation:raise RuntimeError('Home was not saved because the action was cancelled.')
            self.store.save(target)
        return self.status('Shared home saved after confirmed movement.' if action=='motion_set_home' else 'Position confirmed; torque released.')
