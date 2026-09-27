"""Explicit native object tracking, with one camera owner and bounded head steps."""
from __future__ import annotations
import asyncio
import base64
from collections import deque
import contextlib
import time
from .camera_manager import decode_jpeg, settled_thread
from .tracking_target import locate_target, relocate


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
        self.state, self.message = 'STOPPED', 'Open preview, then draw a box around one object.'
        self.frames = deque(maxlen=30)
        self.last_sequence = 0
        self.expected_epoch = None
        self.started = 0
        self.armed = False
        self.home = self.pose = (0,300)
        self.signs = (1,1)
        self.stable = 0
        self.last_box = None
        self.lost_at = None
        self.label = ''
        self._selection_lock = asyncio.Lock()
        self.intent = 0
        self.stop_confirmed = True
        self._last_status = None

    @property
    def active(self): return self.task is not None and not self.task.done()

    def busy(self):
        task=getattr(self.app,'_voice_task',None)
        return task is not None and not task.done()

    def publish(self, message=None):
        if message is not None: self.message=message
        value={'state':self.state,'message':self.message,'armed':self.armed,
               'active':self.active,'head_yaw':self.pose[0]/10,'head_pitch':self.pose[1]/10}
        if value!=self._last_status:
            self._last_status=dict(value)
            self.emit('tracking_status',value)
        return value

    async def stop(self, message='Object tracking stopped.', *, disarm=False):
        self.intent += 1
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
        self.emit('tracking_preview',{})
        self.state='FAULT' if was_active and not self.stop_confirmed else 'STOPPED'
        self.publish('Tracking ended, but UnitV2 stop was not confirmed. Check camera status.' if self.state=='FAULT' else message)

    async def preview(self):
        await self.stop()
        intent = self.intent
        self.camera.check()
        if self.camera.unitv2.mode=='STOPPED': raise RuntimeError('Choose ON DEMAND before object tracking.')
        if self.camera.config.source=='robot-camera': raise RuntimeError('Select UnitV2 or AUTO before object tracking.')
        if not self.camera.unitv2.verified: raise RuntimeError('Pass TEST START / STOP before object tracking.')
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
        self.publish('Hold the object still and draw its box, or enter its name and choose FIND & TRACK.')
        ready=asyncio.get_running_loop().create_future()
        self.task=asyncio.create_task(self._run(ready),name='kadence-object-tracking')
        session=self.task
        self.camera._active=self.task
        self.camera._purpose='tracking'
        self.camera.publish('CAPTURING')
        try:
            async with asyncio.timeout(10): await asyncio.shield(ready)
        except BaseException:
            if self.task is session: await self.stop()
            if ready.done() and not ready.cancelled(): ready.exception()
            else: ready.cancel()
            raise
        return self.publish()

    async def _frame(self):
        result=await self.camera.unitv2.tracking_frame(self.camera.config.address)
        sequence=result.get('sequence')
        if type(sequence) is not int or sequence<=self.last_sequence: raise RuntimeError('Tracker repeated an old image; tracking stopped.')
        self.last_sequence=sequence
        try: jpeg=base64.b64decode(result['image'],validate=True)
        except (KeyError,ValueError,TypeError): raise RuntimeError('Tracker returned an invalid image.') from None
        png,w,h,_=await settled_thread(decode_jpeg,jpeg)
        if (w,h)!=(320,240): raise RuntimeError('Tracker image dimensions changed; tracking stopped.')
        self.camera.check()
        box=result.get('box')
        if box is not None and (not isinstance(box,list) or len(box)!=4 or any(type(v) is not int for v in box)
                or min(box)<0 or min(box[2:])<8 or box[0]+box[2]>640 or box[1]+box[3]>480):
            raise RuntimeError('Tracker returned an invalid target box.')
        self.frames.append((sequence,self.clock(),png))
        self.emit('tracking_preview',{'png':base64.b64encode(png).decode('ascii'),'sequence':sequence,
                                     'box':box if result.get('target_epoch')==self.expected_epoch else None})
        return result

    async def _run(self, ready):
        me=asyncio.current_task()
        generation=self.camera.generation
        try:
            while True:
                self.camera.check(generation)
                if self.clock()-self.started>900: raise RuntimeError('The 15-minute tracking session ended. Start a fresh session when needed.')
                result=await self._frame()
                if not ready.done(): ready.set_result(True)
                if self.state=='TRACKING' and result.get('target_epoch')==self.expected_epoch:
                    await self._follow(result.get('box'))
                await asyncio.sleep(.15)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.armed=False
            self.state='FAULT'
            self.publish(str(exc) if type(exc) is RuntimeError else 'Tracking unavailable. Update UnitV2 using SET UP UNITV2, or check its connection.')
            if not ready.done(): ready.set_exception(RuntimeError(self.message))
        finally:
            await self._settle_move()
            self.frames.clear()
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

    async def select(self, region=None, sequence=None, target=None):
        if self._selection_lock.locked(): raise RuntimeError('Target selection is already running.')
        async with self._selection_lock:
            if not self.active: await self.preview()
            self.operation=asyncio.current_task()
            self.state='FINDING' if target else 'SELECTING'
            self.publish('Selecting the target. Hold it still; the head stays stationary.')
            try:
                if target:
                    reference=self.frames[-1][2]
                    region=await self.locator(reference,target,self.app.settings.providers)
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
                self.stable=0;self.last_box=None;self.lost_at=None
                self.label=target or 'selected object'
                self.state='TRACKING'
                self.publish('Target selected. '+('Head follows after stable fresh matches.' if self.armed else 'Visual tracking only; head following is not armed.'))
                return {'spoken':f'I have selected {self.label}. '+('I will follow it after I finish speaking.' if self.armed else 'I am tracking it on screen. Arm head following in the Tracking tab to move the robot.'), 'message':self.message}
            except BaseException:
                if self.active:
                    self.state='SELECTING';self.expected_epoch=None
                    self.publish('Selection did not complete. Hold the object still and choose it again.')
                raise
            finally: self.operation=None

    async def _follow(self, box):
        if box is None:
            self.stable=0
            if self.lost_at is None: self.lost_at=self.clock()
            self.publish('Target not visible. Head stopped; no blind searching.')
            if self.clock()-self.lost_at>=1.5:
                self.state='LOST'
                self.publish('Target lost. Select it again; automatic reacquisition is disabled.')
            return
        cx,cy=box[0]+box[2]/2,box[1]+box[3]/2
        if self.last_box:
            oldx,oldy=self.last_box[0]+self.last_box[2]/2,self.last_box[1]+self.last_box[3]/2
            if abs(cx-oldx)>160 or abs(cy-oldy)>120:
                self.state='LOST';self.publish('Target jumped too far. Head stopped; select it again.');return
        self.last_box=box
        self.lost_at=None
        self.stable+=1
        if self.stable<3 or not self.armed or self.busy(): return
        dx,dy=(cx-320)/320,(cy-240)/240
        def step(error): return 0 if abs(error)<.13 else max(-20,min(20,round(error*45)))
        yaw=max(self.home[0]-180,min(self.home[0]+180,self.pose[0]+self.signs[0]*step(dx)))
        pitch=max(self.home[1]-150,min(self.home[1]+150,self.pose[1]+self.signs[1]*step(dy)))
        if (yaw,pitch)==self.pose: return
        await self._move((yaw,pitch))
        if self.state=='TRACKING': self.publish('Following the selected target with bounded head steps.')

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

    async def _move(self, pose):
        if self.busy(): raise RuntimeError('Wait for speech to finish before moving the head.')
        body=getattr(self.app,'_body',None)
        if not body or not body.connected: self.armed=False;raise RuntimeError('Robot disconnected; head following disarmed.')
        generation,intent=self.camera.generation,self.intent
        async def send():
            try:
                self.camera.check(generation)
                if intent!=self.intent or self.busy(): raise RuntimeError('Head move superseded before dispatch.')
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
        yaw,pitch=args.get('yaw',0),args.get('pitch',300)
        if type(yaw) is not int or not -140<=yaw<=140 or type(pitch) is not int or not 180<=pitch<=720:
            raise ValueError('Home must be yaw -14..14 degrees and pitch 18..72 degrees.')
        sx,sy=args.get('yaw_sign',1),args.get('pitch_sign',1)
        if type(sx) is not int or sx not in (-1,1) or type(sy) is not int or sy not in (-1,1): raise ValueError('Invalid axis direction.')
        if self.app._last_device_status.get('firmware')!='0.21.6' or self.clock()-getattr(self.app,'_last_device_status_at',0)>5: raise RuntimeError('Head following requires connected firmware 0.21.6 and a fresh device status.')
        self.camera.check()
        self.operation=asyncio.current_task()
        try:
            await self._move((yaw,pitch))
            self.home=(yaw,pitch);self.signs=(sx,sy);self.armed=True
            return self.publish('Home reached and torque released. Head following armed for this server session; select a target.')
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
