"""Quiet physical presence through the existing acknowledged movement owner."""
from __future__ import annotations

import asyncio
import contextlib
import time


class PresenceMotion:
    def __init__(self, app, *, clock=time.monotonic):
        self.app, self.clock = app, clock
        self.task = None
        self.next_at = clock()+35
        self.index = 0
        self.generation = 0
        self.faulted = False

    def permitted(self):
        app = self.app
        camera, motion = app.camera, app.motion
        perception = app.perception
        voice = app._voice_task
        return (not self.faulted and not app._stop.is_set() and not camera.config.privacy
            and camera.config.policy == 'AWARE' and camera.config.perception_enabled
            and app._body is not None and app._body.connected
            and app._last_device_status.get('firmware') in {'0.21.6','0.21.7'}
            and not app._last_device_status.get('media_busy')
            and not app._last_device_status.get('quiet')
            and self.clock()-app._last_device_status_at < 5
            and not (voice and not voice.done())
            and not app.tracking.active and app.tracking.operation is None
            and camera._active is None and not (motion.task and not motion.task.done())
            and perception is not None and perception.gate() == 'ready'
            and perception.occupancy.state == 'OCCUPIED'
            and not (perception.task and not perception.task.done()))

    def tick(self):
        if self.task and not self.task.done(): return
        if self.clock() < self.next_at: return
        if not self.permitted():
            self.next_at = self.clock()+5
            return
        generation = self.generation
        async def move():
            issued = False
            established_home = False
            def guard():
                if generation != self.generation or not self.permitted():
                    raise RuntimeError('Idle movement yielded to another task.')
            try:
                guard()
                home = self.app.motion.store.home
                needs_home = not self.app.motion.store.saved
                offset = (0,0) if needs_home else ((-35,10),(0,0),(35,5),(0,0))[self.index % 4]
                target = (max(-320,min(320,home[0]+offset[0])),max(30,min(870,home[1]+offset[1])))
                # Motion installs its own task before invoking the guard, so
                # ownership is checked here and priority rechecked separately.
                def dispatch_guard():
                    if generation != self.generation or self.app.camera.config.privacy or self.app.camera.config.policy!='AWARE':
                        raise RuntimeError('Idle movement cancelled.')
                    if self.app.tracking.active or self.app.camera._active is not None:
                        raise RuntimeError('Idle movement yielded to the camera.')
                issued = True
                await self.app.motion.move(target, guard=dispatch_guard)
                if needs_home and generation==self.generation:
                    self.app.motion.store.save(target)
                    established_home = True
                if not needs_home: self.index += 1
                self.app.emit('presence_motion', {'state':'settled','message':'Idle glance completed; torque released.'})
            except asyncio.CancelledError: raise
            except Exception:
                if issued and self.app.motion.last_pose is None: self.faulted = True
                self.app.emit('presence_motion', {'state':'paused','message':'Idle movement paused.'})
            finally:
                self.next_at = self.clock()+(5 if established_home else 45)
        self.task = asyncio.create_task(move(), name='kadence-idle-presence')

    async def pause(self):
        self.generation += 1
        self.next_at = self.clock()+35
        task = self.task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await task
        self.task = None
