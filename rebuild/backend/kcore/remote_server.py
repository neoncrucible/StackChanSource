"""Versioned paired LAN client. Never owns serial, camera or conversation state."""
from __future__ import annotations
import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
from .remote_audio import Capture, remote_turn

PROTOCOL=1
PORT=8766
CAMERA_COMMANDS={'privacy_on':'Privacy on','privacy_off':'Privacy off','on_demand':'On demand',
    'keep_ready':'Keep ready','stop':'Stop camera','perception_on':'Perception on','perception_off':'Perception off'}


class RemoteServer:
    def __init__(self, controller):
        self.controller=controller;self.emit=controller.emit
        self.server=None;self.peer=None;self.enabled=False;self.host='';self.port=PORT
        self.state='idle';self.last_error='';self.rssi=None;self.capture=None;self.voice=None
        self.connections=set();self.handlers=set();self.config_lock=asyncio.Lock()
        self.path=controller.services.paths.root/'remote-pairing.json'
        try:
            value=json.loads(self.path.read_text())
            if not re.fullmatch(r'[0-9a-f]{64}',value['key']) or not re.fullmatch(r'[0-9a-f]{16}',value['device_id']):raise ValueError()
            self.pairing=value
        except (OSError,ValueError,KeyError,TypeError):self.pairing=None

    def event(self,event):self.emit('remote_event',{'event':event})

    def status(self):
        value={'enabled':self.enabled,'connected':self.peer is not None,'host':self.host,'port':self.port,
               'paired':self.pairing is not None,'rssi':self.rssi,'mic':'streaming' if self.capture and not self.capture.ready.done() else 'idle',
               'processing':bool(self.voice and not self.voice.done()),'gyro':'unavailable','error':self.last_error}
        if value!=getattr(self,'_last_status',None):
            self._last_status=dict(value);self.emit('remote_status',value)
        return value

    def snapshot(self):
        app=self.controller.app
        camera=app.camera.config if app else None
        connected=bool(app and app._body and app._body.connected)
        return {'v':PROTOCOL,'type':'state.snapshot','robot_link':'tethered','robot_connected':connected,
                'remote_enabled':self.enabled,'kadence_state':self.state if connected else 'disconnected',
                'mic_source':'remote' if self.voice and not self.voice.done() else 'robot',
                'remote_mic_state':'streaming' if self.capture and not self.capture.ready.done() else 'idle',
                'camera_state':('private' if camera.privacy else app.camera.unitv2.status.get('state','UNKNOWN')) if camera else 'unavailable',
                'camera_source':camera.source if camera else 'unavailable','gyro_state':'unavailable',
                'network':{'remote_connected':self.peer is not None,'rssi':self.rssi},
                'capabilities':{'ptt':True,'gyro':False,'camera':CAMERA_COMMANDS,'wireless_robot':False}}

    async def configure(self, args):
        async with self.config_lock:
            if type(args.get('enabled')) is not bool:raise ValueError('Remote ON/OFF must be explicit.')
            await self.close()
            if not args['enabled']:return self.status()
            if not self.pairing:raise RuntimeError('Pair the StickS3 over USB first.')
            host=args.get('host','') or (self.controller.app.settings.lan_host if self.controller.app else '')
            from .audio_network import address_is_local
            try:address=ipaddress.IPv4Address(host)
            except (ValueError,TypeError):raise ValueError('Select this PC LAN IPv4 address.') from None
            if address.is_unspecified or address.is_multicast or address.is_loopback or not address_is_local(host):
                raise ValueError('Remote must bind to an assigned LAN IPv4 address.')
            await self.listen(host,PORT)
            return self.status()

    async def listen(self, host, port):
        from websockets.asyncio.server import serve
        self.host,self.port=host,port
        self.server=await serve(self.handle,host,port,max_size=8192,max_queue=8,write_limit=16384,
            compression=None,ping_interval=5,ping_timeout=5,close_timeout=1,open_timeout=5,origins=[None])
        self.port=self.server.sockets[0].getsockname()[1]
        self.enabled=True;self.last_error='';self.event('enabled')

    async def cancel_voice(self):
        task=self.voice
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(Exception,asyncio.CancelledError):await task
        self.voice=None
        if self.capture:self.capture.close();self.capture=None

    async def close(self):
        self.enabled=False
        if self.voice and not self.voice.done():self.voice.cancel()
        for task in tuple(self.handlers):
            if task is not asyncio.current_task():task.cancel()
        await self.cancel_voice()
        for ws in tuple(self.connections):
            with contextlib.suppress(Exception):await ws.close(code=1001,reason='Remote disabled')
        if self.server:
            self.server.close();await self.server.wait_closed();self.server=None
        self.peer=None;self.rssi=None;self.status()

    async def pair(self, args):
        async with self.config_lock:
            await self.close()
            from .stick_setup import provision
            pairing={'device_id':secrets.token_hex(8),'key':secrets.token_hex(32)}
            args=dict(args)
            if not args.get('host') and self.controller.app:args['host']=self.controller.app.settings.lan_host
            await asyncio.to_thread(provision,args,pairing)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(pairing));tmp.chmod(0o600);tmp.replace(self.path)
            self.pairing=pairing;self.event('paired');return self.status()

    async def send(self, ws, value):
        await asyncio.wait_for(ws.send(json.dumps(value,separators=(',',':'))),2)

    def decode(self, raw):
        if not isinstance(raw,str):raise ValueError('Expected remote JSON message.')
        value=json.loads(raw)
        if not isinstance(value,dict) or type(value.get('v')) is not int or value.get('v')!=PROTOCOL:raise ValueError('Unsupported remote protocol.')
        return value

    async def handle(self, ws):
        task=asyncio.current_task();self.handlers.add(task);self.connections.add(ws)
        pump=None;accepted=False
        try:
            if not self.enabled or len(self.connections)>4 or self.peer or ws.request.path!='/kadence/v1':return
            nonce=secrets.token_hex(32)
            await self.send(ws,{'v':PROTOCOL,'type':'remote.challenge','nonce':nonce})
            hello=self.decode(await asyncio.wait_for(ws.recv(),5))
            device=hello.get('device_id','')
            signature=hmac.new(bytes.fromhex(self.pairing['key']),f'1:{nonce}:{device}'.encode(),hashlib.sha256).hexdigest()
            if set(hello)!={'v','type','device','device_id','proof'} or hello.get('type')!='remote.hello' or hello.get('device')!='StickS3' or device!=self.pairing['device_id'] or not isinstance(hello.get('proof'),str) or not hmac.compare_digest(signature,hello['proof']):
                raise ValueError('Pairing failed.')
            if self.peer or not self.enabled:return
            self.peer=ws;accepted=True;self.event('connected');self.status()
            await self.send(ws,{'v':PROTOCOL,'type':'remote.accept','protocol':PROTOCOL})
            await self.send(ws,self.snapshot())
            pump=asyncio.create_task(self.pump(ws))
            expected=1;window=time.monotonic();count=0
            async for raw in ws:
                if not self.enabled:break
                if isinstance(raw,bytes):
                    if not self.capture:raise ValueError('No active remote capture.')
                    self.capture.frame(raw);continue
                message=self.decode(raw)
                if type(message.get('seq')) is not int or message['seq']!=expected:raise ValueError('Stale remote command.')
                expected+=1;count+=1
                if time.monotonic()-window>1:window=time.monotonic();count=1
                if count>20:raise ValueError('Remote command rate exceeded.')
                try:
                    result=await self.command(message)
                    await self.send(ws,{'v':PROTOCOL,'type':'remote.result','seq':message['seq'],'ok':True,**result})
                except (ValueError,RuntimeError) as exc:
                    if message.get('type','').startswith('audio.'):
                        await self.cancel_voice()
                    await self.send(ws,{'v':PROTOCOL,'type':'remote.result','seq':message['seq'],'ok':False,'message':str(exc)[:160]})
                    self.event('command_rejected')
        except asyncio.CancelledError:raise
        except Exception:
            self.event('connection_rejected' if not accepted else 'connection_lost')
        finally:
            if pump:
                pump.cancel()
                with contextlib.suppress(Exception,asyncio.CancelledError):await pump
            if accepted:
                await self.cancel_voice()
                if self.peer is ws:self.peer=None;self.rssi=None
                self.event('disconnected');self.status()
            self.connections.discard(ws);self.handlers.discard(task)
            with contextlib.suppress(Exception):await ws.close()

    async def pump(self, ws):
        try:
            while True:
                if self.capture and not self.capture.ready.done() and time.monotonic()-self.capture.last>2:
                    await self.cancel_voice();self.event('audio_watchdog')
                    await self.send(ws,{'v':PROTOCOL,'type':'remote.error','message':'Audio stream lost; capture discarded.'})
                if self.capture and self.capture.error and self.last_error!=self.capture.error:
                    self.last_error=self.capture.error
                    await self.send(ws,{'v':PROTOCOL,'type':'remote.error','message':self.last_error})
                app=self.controller.app
                if self.voice and (not app or not app._body or not app._body.connected):await self.cancel_voice()
                self.status()
                await self.send(ws,self.snapshot())
                await asyncio.sleep(.5)
        except asyncio.CancelledError:raise
        except Exception:
            await ws.close()

    async def command(self, message):
        name=message.get('type')
        fields={'remote.ping':{'rssi'},'audio.start':set(),'audio.stop':{'capture','frames'},'camera.set':{'command'}}
        if name not in fields or set(message)!={'v','seq','type'}|fields[name]:raise ValueError('Unsupported remote fields.')
        if name=='remote.ping':
            rssi=message.get('rssi')
            if type(rssi) is not int or not -127<=rssi<=0:raise ValueError('Invalid RSSI.')
            self.rssi=rssi;return {}
        app=self.controller.app
        if not app or not app._body or not app._body.connected:raise RuntimeError('Robot is disconnected.')
        if name=='audio.start':
            if app._voice_task and not app._voice_task.done():raise RuntimeError('Kadence is busy; try again when idle.')
            if self.controller._media and not self.controller._media.done():raise RuntimeError('Finish the current camera operation first.')
            if app.settings.providers.missing_credentials():raise RuntimeError('Voice service credentials are missing.')
            if self.capture:self.capture.close()
            self.last_error=''
            self.capture=Capture(secrets.randbits(32))
            self.voice=app._voice_task=asyncio.create_task(remote_turn(app,self.capture),name='kadence-remote-voice')
            self.voice.add_done_callback(app._voice_task_done)
            self.event('audio_start');return {'capture':self.capture.ident,'sample_rate':16000,'frame_samples':640}
        if name=='audio.stop':
            if not self.capture:raise ValueError('No active remote capture.')
            self.capture.finish(message.get('capture'),message.get('frames'))
            self.event('audio_stop');return {}
        if name=='camera.set':
            command=message.get('command')
            if command not in CAMERA_COMMANDS:raise ValueError('Unsupported camera state.')
            if app._voice_task and not app._voice_task.done():raise RuntimeError('Wait for voice to finish before changing the camera.')
            result=await self.controller.camera_voice(command)
            if result.get('ok') is False:raise RuntimeError(result['spoken'])
            self.event('camera_command');return {'message':result['spoken']}
        raise ValueError('Unsupported remote command.')
