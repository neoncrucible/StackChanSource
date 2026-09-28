"""Live factory algorithms under CameraManager ownership; no motor authority."""
from __future__ import annotations
import asyncio
import base64
import contextlib
import json
import time
from .camera_manager import decode_jpeg, settled_thread

MODES = {
    'color_tracker':'Colour Tracker', 'shape_detector':'Shape Detector',
    'shape_matching':'Shape Matching', 'motion_tracker':'Motion Tracker',
    'code_detector':'Code Detector', 'object_recognition':'Object Recognition',
    'face_detector':'Face Detector', 'lane_line_tracker':'Lane Line Tracker',
    'online_classifier':'Online Classifier', 'audio_fft':'Audio FFT',
}


class FactoryVision:
    def __init__(self, app):
        self.app,self.camera=app,app.camera
        self.task=None
        self.mode=None
        self.state='STOPPED'
        self.message='Choose a factory mode, then Start. These modes do not move the robot.'
        self.sequence=0
        self.last_at=0
        self.result={}
        self.png=None
        self.intent=0

    @property
    def active(self): return self.task is not None and not self.task.done()

    def publish(self):
        value={'state':self.state,'mode':self.mode,'message':self.message,'active':self.active}
        self.app.emit('factory_status',value)
        return value

    async def stop(self):
        self.intent+=1
        task=self.task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError,Exception): await task
        self.png=None
        self.result={}
        self.app.emit('factory_preview',{})
        return self.publish()

    async def start(self, mode):
        if mode not in MODES: raise ValueError('Choose a supported factory mode.')
        await self.app.tracking.stop(disarm=True)
        await self.stop()
        intent=self.intent
        self.camera.check()
        if self.camera.config.source=='robot-camera': raise RuntimeError('Select UnitV2 or AUTO first.')
        if self.camera.unitv2.mode=='STOPPED': raise RuntimeError('Choose ON DEMAND first.')
        if not self.camera.unitv2.verified: raise RuntimeError('Pass TEST START / STOP first.')
        perception=getattr(self.app,'perception',None)
        if perception: await perception.interrupt()
        if intent!=self.intent: raise RuntimeError('Factory start was superseded by Stop.')
        if self.camera._active is not None: raise RuntimeError('Camera is busy. Finish its current action first.')
        self.mode,self.state,self.sequence=mode,'STARTING',0
        self.message='Starting '+MODES[mode]+' on UnitV2.'
        ready=asyncio.get_running_loop().create_future()
        self.task=asyncio.create_task(self._run(ready),name='kadence-factory-vision')
        self.camera._active,self.camera._purpose=self.task,'factory'
        self.camera.publish('CAPTURING')
        self.publish()
        try:
            async with asyncio.timeout(15): await asyncio.shield(ready)
        except BaseException:
            await self.stop()
            if ready.done() and not ready.cancelled(): ready.exception()
            else: ready.cancel()
            raise
        return self.publish()

    async def _run(self, ready):
        me=asyncio.current_task()
        generation=self.camera.generation
        started=time.monotonic()
        try:
            while True:
                self.camera.check(generation)
                if time.monotonic()-started>900: raise RuntimeError('The 15-minute factory session ended. Start again when needed.')
                value=await self.camera.unitv2.factory_frame(self.camera.config.address,self.mode)
                sequence=value.get('result_sequence')
                if type(sequence) is not int or sequence<=self.sequence: raise RuntimeError('Factory result repeated; stopped.')
                self.sequence=sequence
                self.result=value.get('result',{})
                self.last_at=time.monotonic()
                png=None
                if value.get('image'):
                    jpeg=base64.b64decode(value['image'],validate=True)
                    png,_,_,_=await settled_thread(decode_jpeg,jpeg)
                self.camera.check(generation)
                self.png=png
                self.state='RUNNING'
                self.message=value.get('message') or MODES[self.mode]+' is live on UnitV2.'
                self.app.emit('factory_preview',{'png':base64.b64encode(png).decode() if png else '',
                    'sequence':sequence,'result':self.result,'mode':self.mode})
                self.publish()
                if not ready.done(): ready.set_result(True)
                await asyncio.sleep(.2)
        except asyncio.CancelledError: raise
        except Exception as exc:
            self.state='FAULT'
            self.message=str(exc) if isinstance(exc,RuntimeError) else 'Factory mode unavailable. Check UnitV2 setup and connection.'
            if not ready.done(): ready.set_exception(RuntimeError(self.message))
        finally:
            stop=asyncio.create_task(self.camera.unitv2.stop())
            while not stop.done():
                try: await asyncio.shield(stop)
                except asyncio.CancelledError: continue
                except Exception: break
            try:
                stop.result()
                if self.camera.unitv2.status.get('stop_confirmed') is not True: raise RuntimeError()
                if self.state!='FAULT': self.state,self.message='STOPPED','Factory mode stopped; producer stop confirmed.'
            except (Exception,asyncio.CancelledError):
                self.state,self.message='FAULT','Factory session ended; producer stop was NOT confirmed. Check UnitV2 status.'
            self.png=None
            self.result={}
            if self.camera._active is me:
                self.camera._active=self.camera._purpose=None
                self.camera.publish('IDLE')
            if self.task is me: self.task=None
            self.app.emit('factory_preview',{})
            self.publish()

    async def configure(self, config, *, region=None, sequence=None):
        if not self.active: raise RuntimeError('Start a factory mode first.')
        if region is not None:
            if sequence!=self.sequence or time.monotonic()-self.last_at>3: raise RuntimeError('Preview changed. Select the colour again.')
            if not isinstance(region,list) or len(region)!=4 or any(type(v) is not int for v in region): raise ValueError('Invalid region')
            config=dict(zip(('x','y','w','h'),[round(v*scale/1000) for v,scale in zip(region,(640,480,640,480))]))
        self.camera.check()
        result=await self.camera.unitv2.factory_frame(self.camera.config.address,self.mode,config)
        self.message=result.get('message','Configuration sent.')
        return self.publish()

    def summary(self):
        if not self.active or time.monotonic()-self.last_at>3: return 'No live factory result. Start a mode in Factory Vision.'
        result=self.result
        if self.mode=='shape_detector' or self.mode=='shape_matching':
            names=[str(x.get('name','unidentified')) for x in result.get('shape',[]) if isinstance(x,dict)]
            return 'Shapes: '+(', '.join(names[:8]) if names else 'none detected in the latest frame')+'.'
        if self.mode=='color_tracker':
            return 'The selected colour '+('is detected.' if result.get('r',0)>0 else 'is not detected in the latest frame.')
        return MODES[self.mode]+': '+json.dumps(result,ensure_ascii=False)[:1000]
