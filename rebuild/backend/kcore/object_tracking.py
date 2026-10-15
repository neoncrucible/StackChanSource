"""Explicit native object tracking, with one camera owner and bounded head steps."""
from __future__ import annotations
import asyncio
import base64
from collections import deque
import contextlib
import io
import json
from pathlib import Path
import time
from .camera_manager import settled_thread
from .tracking_target import locate_target, relocate, local_target, POINTING_TARGETS


def validate_preview(jpeg):
    from PIL import Image
    if len(jpeg)>2*1024*1024: raise RuntimeError('Tracker image exceeds limit.')
    with Image.open(io.BytesIO(jpeg)) as image:
        if image.format!='JPEG' or image.size!=(320,240):
            raise RuntimeError('Tracker image dimensions changed; tracking stopped.')
        image.load()


def diagnostic_status(value):
    if value.get('state') not in {'STOPPED','STOPPING','SELECTING','FINDING','TRACKING','LOST','FAULT'}: return None
    safe={'state':value['state']}
    for key in ('armed','active'):
        if type(value.get(key)) is bool: safe[key]=value[key]
    for key,low,high in (('head_yaw',-32,32),('head_pitch',3,87)):
        item=value.get(key)
        if type(item) in (int,float) and low<=item<=high: safe[key]=item
    return safe


class ObjectTracking:
    def __init__(self, app, *, clock=time.monotonic, locator=locate_target):
        self.app, self.camera, self.emit = app, app.camera, app.emit
        self.clock, self.locator = clock, locator
        self.camera.tracking = self
        self.task = self.operation = self.move = None
        self._follow_task = None
        self._head_ready_at = 0
        self.state, self.message = 'STOPPED', 'Say “track that” or name the object you want me to follow.'
        self.frames = deque(maxlen=30)
        self.last_sequence = 0
        self.expected_epoch = None
        self.started = 0
        self.armed = False
        self._home = self.pose = (0,300)
        self.signs = (1,1)
        self.stable = 0
        self.last_box = None
        self.lost_at = None
        self.label = ''
        self._selection_lock = asyncio.Lock()
        self.intent = 0
        self.stop_confirmed = True
        self._last_status = None
        self._last_preview = 0
        self._last_metrics = 0
        self._last_good = None
        self._recovered = 0
        self._observation = None
        self._pending_head = None
        self.watch_box = None
        self.watch_since = None
        self._notice = None
        self._signature = None

    def request_head_setup(self):
        saved = self.saved_head_setup()
        if saved: return saved
        # A spoken follow request authorises following on the existing robot.
        # Older accepted installs used 0/30 degrees without persisting a home.
        # Establish that existing baseline through an acknowledged move when
        # needed; never write the servo zero calibration or ask for an arm toggle.
        motion = getattr(self.app, 'motion', None)
        if motion:
            return {'mounted': True, 'yaw_sign': 1, 'pitch_sign': 1,
                'bootstrap_home':not motion.store.saved}
        return None

    def _save_head_setup(self):
        path=self.head_setup_path()
        if path:
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'format':1,'home':list(self.home),
                'yaw_sign':self.signs[0],'pitch_sign':self.signs[1]}))
            temporary.replace(path)

    async def current_frame(self):
        """Borrow a NEW image from the existing lease; never start a second producer."""
        from .camera_manager import CameraFrame, decode_jpeg
        if not self.active: raise RuntimeError('Tracking camera is not running.')
        after = self.last_sequence
        async with asyncio.timeout(3):
            while self.active and (not self.frames or self.frames[-1][0] <= after):
                await asyncio.sleep(.02)
            self.camera.check()
            if not self.active or not self.frames: raise RuntimeError('Tracking camera stopped before a fresh image arrived.')
            sequence, captured, jpeg = self.frames[-1]
            png, width, height, qr = await settled_thread(decode_jpeg, jpeg)
            self.camera.check()
            return CameraFrame('tracking-look', str(sequence), 'unitv2-camera', png, width, height,
                time.time() - max(0, self.clock()-captured), 0, self.camera.generation, tuple(qr))

    async def watch(self, target):
        reuse = target.casefold().strip() in POINTING_TARGETS or target.casefold().strip() == self.label.casefold().strip()
        self._pending_head = None
        self.armed = False
        await self.pause_head()
        if not (reuse and self.active and self.state == 'TRACKING' and self.last_box):
            await self.select(target=target, follow=False)
        if not self.last_box: raise RuntimeError("I haven't locked onto it yet, Boss. Hold it in view and ask again.")
        self.watch_box = list(self.last_box)
        self.watch_since = None
        self._notice = None
        self.started = self.clock()
        message = f"I'm watching {self.label} for fifteen minutes, Boss. I'll tell you if it moves or I lose sight of it."
        self.publish(message)
        return {'spoken': message, 'watching': True}

    def _watch_observation(self, box):
        if self.watch_box is None: return
        old = self.watch_box
        moved = box is not None and ((box[0]+box[2]/2-old[0]-old[2]/2)**2 +
            (box[1]+box[3]/2-old[1]-old[3]/2)**2)**.5 > max(28, min(old[2:])*.3)
        kind = 'lost' if box is None else 'moved' if moved else None
        if kind is None:
            self.watch_since = None
            return
        if self.watch_since is None or self.watch_since[0] != kind:
            self.watch_since = (kind, self.clock(), 1)
            return
        kind, started, count = self.watch_since
        self.watch_since = (kind, started, count+1)
        if count < 3 or self.clock()-started < 1.5: return
        message = (f"Boss, {self.label} moved." if kind == 'moved' else
            f"Boss, I've lost sight of {self.label}. It may be covered or out of view.")
        self._notice = (message, self.clock(), self.intent, self.camera.generation)
        self.watch_box = None  # One notification per explicitly armed watch.
        self.emit('tracking_notice', {'message': message, 'reason': kind})
        self.publish(message)

    def take_notice(self):
        notice, self._notice = self._notice, None
        if notice and self.clock()-notice[1] < 20 and notice[2:] == (self.intent, self.camera.generation):
            return notice[0]
        return None

    def head_setup_path(self):
        services=getattr(self.app,'services',None)
        return Path(services.paths.root)/'tracking-head.json' if services else None

    def saved_head_setup(self):
        path=self.head_setup_path()
        if path is None: return None
        try:
            value=json.loads(path.read_text())
            if (value.get('format')==1 and value.get('home')==list(self.home)
                    and all(type(value.get(k)) is int and value[k] in (-1,1) for k in ('yaw_sign','pitch_sign'))):
                return {'mounted':True,'yaw_sign':value['yaw_sign'],'pitch_sign':value['pitch_sign']}
        except (OSError,ValueError,AttributeError): pass
        return None

    @property
    def home(self):
        motion=getattr(self.app,'motion',None)
        return motion.store.home if motion else self._home

    @home.setter
    def home(self,value):
        self._home=value  # compatibility for isolated controller fixtures only

    @property
    def active(self): return self.task is not None and not self.task.done()

    def busy(self):
        task=getattr(self.app,'_voice_task',None)
        return task is not None and not task.done()

    def publish(self, message=None):
        if message is not None: self.message=message
        value={'state':self.state,'message':self.message,'armed':self.armed,
               'active':self.active,'head_yaw':self.pose[0]/10,'head_pitch':self.pose[1]/10,
               'head_pending':self._pending_head is not None,'watching':self.watch_box is not None,
               'source':'unitv2-camera'}
        if value!=self._last_status:
            self._last_status=dict(value)
            self.emit('tracking_status',value)
        return value

    async def stop(self, message='Object tracking stopped.', *, disarm=False):
        self.intent += 1
        self._pending_head = None
        self.watch_box = self.watch_since = self._notice = None
        was_active = self.active
        if disarm: self.armed=False
        if self.active or self.move is not None:
            self.state='STOPPING'
            self.publish('Stopping tracking; waiting for any bounded head step to release torque.')
            self.emit('tracking_preview',{})
        current=asyncio.current_task()
        op=self.operation
        if op and op is not current and not op.done():
            op.cancel()
            with contextlib.suppress(asyncio.CancelledError,Exception): await op
        task=self.task
        if task and task is not current and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError,Exception): await task
        await self._settle_move()
        self.frames.clear()
        self._signature=None
        self._last_good=None
        self._recovered=0
        self.emit('tracking_preview',{})
        self.state='FAULT' if was_active and not self.stop_confirmed else 'STOPPED'
        self.publish('Tracking ended, but UnitV2 stop was not confirmed. Check camera status.' if self.state=='FAULT' else message)

    async def preview(self):
        await self.stop()
        intent = self.intent
        self.camera.check()
        # Tracking is an explicit UnitV2 capability request; it does not need a
        # separate camera-mode toggle or change the saved snapshot preference.
        pc=getattr(self.app,'perception',None)
        if pc: await pc.interrupt()
        if intent != self.intent: raise RuntimeError('Tracking start was superseded by Stop.')
        if self.camera._active is not None: raise RuntimeError('Camera is busy. Finish its current action first.')
        self.last_sequence=0
        self.expected_epoch=None
        self.stable=0
        self.last_box=None
        self.lost_at=None
        self.label=''
        self.started=self.clock()
        self.state='SELECTING'
        self.stop_confirmed=False
        self.publish('Camera ready. Say “track that” or name one object in view.')
        ready=asyncio.get_running_loop().create_future()
        self.task=asyncio.create_task(self._run(ready),name='kadence-object-tracking')
        session=self.task
        self.camera._active=self.task
        self.camera._purpose='tracking'
        self.camera.publish('CAPTURING')
        try:
            async with asyncio.timeout(25): await asyncio.shield(ready)
        except BaseException:
            if self.task is session: await self.stop()
            if ready.done() and not ready.cancelled(): ready.exception()
            else: ready.cancel()
            raise
        return self.publish()

    async def _frame(self):
        started=self.clock()
        result=await self.camera.unitv2.tracking_frame(self.camera.config.address)
        sequence=result.get('sequence')
        if type(sequence) is not int or sequence<=self.last_sequence: raise RuntimeError('Tracker repeated an old image; tracking stopped.')
        self.last_sequence=sequence
        try: jpeg=base64.b64decode(result['image'],validate=True)
        except (KeyError,ValueError,TypeError): raise RuntimeError('Tracker returned an invalid image.') from None
        # Preserve the native JPEG: PNG conversion inflated every preview and
        # held the control loop behind compression and UI-pipe writes.
        await settled_thread(validate_preview,jpeg)
        self.camera.check()
        box=result.get('box')
        if box is not None and (not isinstance(box,list) or len(box)!=4 or any(type(v) is not int for v in box)
                or min(box)<0 or min(box[2:])<8 or box[0]+box[2]>640 or box[1]+box[3]>480):
            raise RuntimeError('Tracker returned an invalid target box.')
        now=self.clock()
        self.frames.append((sequence,now,jpeg))
        self._observation = result
        if now-self._last_preview>=.08:
            self._last_preview=now
            self.emit('tracking_preview',{'jpeg':result['image'],'sequence':sequence,
                                         'box':box if result.get('target_epoch')==self.expected_epoch else None})
        if now-self._last_metrics>=1:
            self._last_metrics=now
            self.emit('tracking_timing',{'frame_ms':round((now-started)*1000)})
        return result

    async def _run(self, ready):
        me=asyncio.current_task()
        generation=self.camera.generation
        try:
            await self.camera.unitv2.ensure_ready(self.camera.config.address,
                guard=lambda: self.camera.check(generation))
            while True:
                self.camera.check(generation)
                if self.clock()-self.started>900: raise RuntimeError('The 15-minute tracking session ended. Start a fresh session when needed.')
                result=await self._frame()
                if not ready.done(): ready.set_result(True)
                following=self._follow_task
                if following and following.done():
                    self._follow_task=None
                    if not following.cancelled(): following.result()
                if self.state=='TRACKING' and result.get('target_epoch')==self.expected_epoch and self._follow_task is None:
                    # Keep receiving fresh images while the one bounded motor
                    # command waits for its acknowledgement. Never queue steps.
                    self._follow_task=asyncio.create_task(self._follow(result.get('box'), self.frames[-1][2]),name='kadence-follow-step')
                elif self.state=='LOST' and result.get('target_epoch')==self.expected_epoch:
                    self._watch_observation(result.get('box'))
                    await self._recover(result.get('box'))
                # UnitV2's authenticated observation already waits for a new
                # image. Polling again immediately cannot replay an old frame.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.armed=False
            self.state='FAULT'
            self.publish(str(exc) if type(exc) is RuntimeError else 'Tracking unavailable. Update UnitV2 using SET UP UNITV2, or check its connection.')
            if not ready.done(): ready.set_exception(RuntimeError(self.message))
        finally:
            await self.pause_head()
            self.frames.clear()
            self._last_good=None
            self.emit('tracking_preview',{})
            stopping=asyncio.create_task(self.camera.unitv2.stop(),name='kadence-tracker-camera-stop')
            while not stopping.done():
                try: await asyncio.shield(stopping)
                except asyncio.CancelledError: continue
                except Exception: break
            try:
                stopping.result()
                self.stop_confirmed=self.camera.unitv2.status.get('stop_confirmed') is True
                if not self.stop_confirmed: raise RuntimeError('Camera stop unconfirmed')
            except (Exception,asyncio.CancelledError):
                self.state='FAULT';self.publish('Tracking stopped, but camera stop was not confirmed. Check UnitV2 status.')
            if self.state not in {'FAULT','LOST'}: self.state='STOPPED'
            if self.camera._active is me:
                self.camera._active=None;self.camera._purpose=None;self.camera.publish('IDLE')
            if self.task is me: self.task=None
            self.publish()

    async def select(self, region=None, sequence=None, target=None, *, follow=True):
        setup=self.request_head_setup() if target and follow and not self.armed else None
        if setup and not self.busy(): await self.arm(setup)
        if self._selection_lock.locked(): raise RuntimeError('Target selection is already running.')
        async with self._selection_lock:
            if not self.active: await self.preview()
            self.watch_box = self.watch_since = self._notice = None
            self.operation=asyncio.current_task()
            self.state='FINDING' if target else 'SELECTING'
            try:
                intent=self.intent
                await self.pause_head()
                if asyncio.current_task().cancelling(): raise asyncio.CancelledError
                if intent!=self.intent: raise RuntimeError('Target selection was superseded by Stop.')
                self.camera.check()
                self.publish('Selecting the target. Hold it still; the head stays stationary.')
                if target:
                    reference=self.frames[-1][2]
                    selected_at=self.clock()
                    earlier=next((f[2] for f in reversed(self.frames) if self.clock()-f[1]>=.2),None)
                    if earlier is None and target.casefold().strip() in POINTING_TARGETS:
                        # A newly opened preview has only one image. Give the
                        # presented object a short local observation window
                        # rather than always falling through to cloud vision.
                        earlier=reference
                        await asyncio.sleep(.25)
                        self.camera.check()
                        if not self.active or not self.frames: raise RuntimeError('Tracking session ended during selection.')
                        reference=self.frames[-1][2]
                    region=await settled_thread(local_target,reference,target,earlier)
                    if region is None:
                        region=await self.locator(reference,target,self.app.settings.providers)
                    self.emit('tracking_timing',{'selection_ms':round((self.clock()-selected_at)*1000)})
                else:
                    frame=next((f for f in self.frames if f[0]==sequence and self.clock()-f[1]<8),None)
                    if frame is None: raise RuntimeError('That preview expired. Draw a new box on the current image.')
                    reference=frame[2]
                if not self.active or not self.frames: raise RuntimeError('Tracking session ended during selection.')
                self.camera.check()
                roi=await settled_thread(relocate,reference,self.frames[-1][2],region)
                generation=self.camera.generation
                result=await self.camera.unitv2.tracking_frame(self.camera.config.address,roi=roi)
                self.camera.check(generation)
                self.expected_epoch=result['target_epoch']
                # An ROI acknowledgement is not evidence of tracking. Require
                # two distinct live target reports before saying it is locked.
                after=self.last_sequence
                observed=0
                async with asyncio.timeout(3):
                    while observed<2:
                        await asyncio.sleep(.02)
                        self.camera.check(generation)
                        if intent!=self.intent or not self.active: raise RuntimeError('Tracking selection was cancelled.')
                        current=self._observation
                        if current and current['sequence']>after:
                            after=current['sequence']
                            good=current.get('target_epoch')==self.expected_epoch and current.get('box') is not None
                            observed=observed+1 if good else 0
                self.stable=0;self.last_box=list(current['box']);self.lost_at=None
                from .tracking_evidence import signature
                self._signature=await settled_thread(signature, self.frames[-1][2], self.last_box)
                self.label=target or 'selected object'
                self._pending_head=setup if setup and not self.armed and follow else None
                self.state='TRACKING'
                if not follow:
                    spoken=f'Locked onto {self.label}.'
                elif self._pending_head:
                    spoken=f"Locked onto {self.label}, Boss. Head following starts when I finish speaking."
                elif self.armed:
                    spoken=f'I am tracking {self.label}, Boss. Head following is enabled.'
                else:
                    spoken=f"Camera tracking is active for {self.label}, Boss, but my head's home position needs setting once in Motion before I can follow physically."
                self.publish(spoken)
                return {'spoken':spoken, 'message':self.message, 'target_confirmed':True,
                    'head_following':self.armed, 'head_pending':self._pending_head is not None}
            except TimeoutError:
                self.state='SELECTING';self.expected_epoch=None
                self.publish("I couldn't keep a lock on that object. Hold it clearly in view and ask again.")
                raise RuntimeError(self.message) from None
            except BaseException:
                if self.active:
                    self.state='SELECTING';self.expected_epoch=None
                    self.publish('Selection did not complete. Hold the object still and choose it again.')
                raise
            finally: self.operation=None

    async def _follow(self, box, image=None):
        if box is not None and self._signature is not None and (image or self.frames):
            from .tracking_evidence import agrees
            if not await settled_thread(agrees, self._signature, image or self.frames[-1][2], box):
                box=None
        self._watch_observation(box)
        if box is None:
            self.stable=0
            if self.lost_at is None: self.lost_at=self.clock()
            self.publish('Target not visible. Head stopped; no blind searching.')
            if self.clock()-self.lost_at>=1.5:
                self.state='LOST'
                self.publish('Target briefly lost. I will resume if I can verify the same object in view.')
            return
        cx,cy=box[0]+box[2]/2,box[1]+box[3]/2
        if self.last_box:
            oldx,oldy=self.last_box[0]+self.last_box[2]/2,self.last_box[1]+self.last_box[3]/2
            if abs(cx-oldx)>160 or abs(cy-oldy)>120:
                self.state='LOST';self.lost_at=None
                self.publish('Target changed abruptly. Show it clearly and say “track that” again.');return
        self.last_box=box
        if self.frames: self._last_good=(self.frames[-1][2],list(box))
        self.lost_at=None
        self.stable+=1
        if self._pending_head and not self.busy() and self.stable>=3:
            setup=self._pending_head
            self._pending_head=None
            self.signs=(setup['yaw_sign'],setup['pitch_sign'])
            if self.app._last_device_status.get('firmware')!='0.21.6' or self.clock()-self.app._last_device_status_at>5:
                raise RuntimeError('Head following needs a fresh robot connection. The visual target is still available.')
            # Establish a known physical origin once for this follow request.
            # Ordinary conversation never resets an already armed tracker.
            await self._move(self.home)
            if setup.get('bootstrap_home') and getattr(self.app,'motion',None):
                self.app.motion.store.save(self.home)
            self.armed=True
            self._save_head_setup()
            self.publish('Target locked; head following enabled.')
        if self.stable<3 or not self.armed or self.busy() or self.clock()<self._head_ready_at: return
        dx,dy=(cx-320)/320,(cy-240)/240
        def step(error): return 0 if abs(error)<.13 else max(-20,min(20,round(error*45)))
        yaw=max(self.home[0]-180,min(self.home[0]+180,self.pose[0]+self.signs[0]*step(dx)))
        pitch=max(self.home[1]-150,min(self.home[1]+150,self.pose[1]+self.signs[1]*step(dy)))
        if (yaw,pitch)==self.pose: return
        yaw=max(-320,min(320,yaw));pitch=max(30,min(870,pitch))
        await self._move((yaw,pitch))
        # The old preview sleep also limited servo cadence. Keep that physical
        # settling interval while allowing camera frames to arrive continuously.
        self._head_ready_at=self.clock()+.15
        if self.state=='TRACKING': self.publish('Following the selected target with bounded head steps.')

    async def _recover(self, box):
        # Brief occlusion only: require appearance agreement with the last
        # known target, a matching native epoch, and three fresh observations.
        # No motor search and no cloud call can silently pick a different item.
        if box is None or not self._last_good or self.lost_at is None or self.clock()-self.lost_at>5:
            self._recovered=0
            return
        reference,previous=self._last_good
        region=[round(v*1000/s) for v,s in zip(previous,(640,480,640,480))]
        try: checked=await settled_thread(relocate,reference,self.frames[-1][2],region)
        except (RuntimeError,ValueError):
            self._recovered=0
            return
        if any(abs(a-b)>32 for a,b in zip(checked,box)):
            self._recovered=0
            return
        self._recovered+=1
        if self._recovered>=3:
            self.state='TRACKING';self.stable=0;self.last_box=None;self.lost_at=None;self._recovered=0
            self.publish('Same target found. Tracking resumed.')

    async def _settle_move(self):
        task=self.move
        if task is None: return
        # Do not abandon an in-flight physical move on task cancellation. The
        # existing firmware bounds each move and releases torque before ACK.
        while not task.done():
            try: await asyncio.shield(task)
            except asyncio.CancelledError: continue
            except Exception: break
        with contextlib.suppress(Exception,asyncio.CancelledError): task.result()
        if self.move is task: self.move=None

    async def pause_head(self):
        task=self._follow_task
        if task:
            if not task.done(): task.cancel()
            while not task.done():
                try: await asyncio.shield(task)
                except (asyncio.CancelledError,Exception): continue
            with contextlib.suppress(asyncio.CancelledError,Exception): task.result()
            if self._follow_task is task: self._follow_task=None
        await self._settle_move()

    async def _move(self, pose):
        if self.busy(): raise RuntimeError('Wait for speech to finish before moving the head.')
        body=getattr(self.app,'_body',None)
        if not body or not body.connected: self.armed=False;raise RuntimeError('Robot disconnected; head following disarmed.')
        generation,intent=self.camera.generation,self.intent
        async def send():
            try:
                self.camera.check(generation)
                if intent!=self.intent or self.busy(): raise RuntimeError('Head move superseded before dispatch.')
                motion=getattr(self.app,'motion',None)
                if motion:
                    def guard():
                        self.camera.check(generation)
                        if intent!=self.intent: raise RuntimeError('Head move superseded.')
                    await motion.move(pose,guard=guard)
                    self.pose=pose
                    return
                ack=await body.send_body_pose(*pose,timeout=10)
                if any(ack.payload.get(k) is not True for k in ('ok','executed','torque_released')):
                    raise RuntimeError('Head move did not confirm torque release; following disarmed.')
                self.pose=pose
            except BaseException:
                self.armed=False
                raise
        self.move=asyncio.create_task(send(),name='kadence-tracking-pose')
        try: await asyncio.shield(self.move)
        finally: await self._settle_move()

    async def arm(self, args):
        await self.stop(disarm=True)
        intent=self.intent
        pc=getattr(self.app,"perception",None)
        if pc: await pc.interrupt()
        if intent!=self.intent: raise RuntimeError("Head action was superseded by Stop.")
        if args.get('mounted') is not True: raise ValueError('Head following requires UnitV2 mounted on the moving head.')
        yaw,pitch=self.home
        if getattr(self.app,'motion',None) and not self.app.motion.store.saved and not args.get('bootstrap_home'):
            raise RuntimeError('Set the shared home in Motion before arming head following.')
        sx,sy=args.get('yaw_sign',1),args.get('pitch_sign',1)
        if type(sx) is not int or sx not in (-1,1) or type(sy) is not int or sy not in (-1,1): raise ValueError('Invalid axis direction.')
        if self.app._last_device_status.get('firmware')!='0.21.6' or self.clock()-getattr(self.app,'_last_device_status_at',0)>5: raise RuntimeError('Head following requires connected firmware 0.21.6 and a fresh device status.')
        self.camera.check()
        self.operation=asyncio.current_task()
        try:
            await self._move((yaw,pitch))
            if intent!=self.intent: raise RuntimeError('Head setup was cancelled before saving.')
            if args.get('bootstrap_home') and getattr(self.app,'motion',None):
                self.app.motion.store.save((yaw,pitch))
            self.home=(yaw,pitch);self.signs=(sx,sy);self.armed=True
            self._save_head_setup()
            return self.publish('Head setup saved. Say “follow this pen” whenever you want to track an object.')
        finally: self.operation=None

    async def home_head(self):
        if not self.armed: raise RuntimeError('Set and arm the home pose first.')
        await self.stop()
        intent=self.intent
        pc=getattr(self.app,"perception",None)
        if pc: await pc.interrupt()
        if intent!=self.intent: raise RuntimeError("Head action was superseded by Stop.")
        self.camera.check()
        self.operation=asyncio.current_task()
        try:
            await self._move(self.home)
            return self.publish('Returned home; torque released.')
        finally: self.operation=None
