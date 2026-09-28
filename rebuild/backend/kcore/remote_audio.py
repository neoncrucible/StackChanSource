"""Disk-backed PTT capture. Duration is controlled by release, never robot timing."""
from __future__ import annotations
import asyncio
import contextlib
import io
import shutil
import struct
import tempfile
import time
import wave
from .voice_providers import VoiceNoSpeechDetected

RATE=16000
FRAME_BYTES=1280 # 40 ms mono PCM16


class Capture:
    def __init__(self, ident, *, clock=time.monotonic):
        self.ident,self.clock=ident,clock
        self.file=tempfile.TemporaryFile(prefix='kadence-ptt-')
        self.sequence=0;self.samples=0;self.last=clock();self.started=self.last
        self.ready=asyncio.get_running_loop().create_future()
        self.closed=False;self.error=''

    def frame(self, data):
        if self.closed or self.ready.done():raise ValueError('Capture is not streaming.')
        if len(data)!=8+FRAME_BYTES:raise ValueError('Invalid remote audio frame.')
        ident,seq=struct.unpack('!II',data[:8])
        if ident!=self.ident or seq!=self.sequence:raise ValueError('Remote audio sequence mismatch.')
        # A peer may not flood hours of fabricated PCM in a few seconds.
        if self.samples/RATE>self.clock()-self.started+2:raise ValueError('Remote audio arrived too quickly.')
        if self.sequence%250==0 and shutil.disk_usage(tempfile.gettempdir()).free<64*1024*1024:
            raise RuntimeError('Not enough temporary storage for remote audio.')
        self.file.write(data[8:]);self.samples+=FRAME_BYTES//2;self.sequence+=1;self.last=self.clock()

    def finish(self, ident, frames):
        if self.closed or self.ready.done() or type(ident) is not int or type(frames) is not int or ident!=self.ident or frames!=self.sequence or not frames:
            raise ValueError('Remote capture was incomplete.')
        self.file.flush();self.file.seek(0);self.ready.set_result(True)

    async def transcribe(self, stt):
        # Each request is bounded; total deliberate PTT duration has no fixed cap.
        # Chunking keeps provider upload and host memory limits independent of PTT.
        words=[];overlap=b''
        while True:
            pcm=self.file.read(RATE*2*30)
            if not pcm:break
            current=pcm
            pcm=overlap+pcm
            overlap=current[-16000:]  # half-second context across 30-second upload boundaries
            wav=io.BytesIO()
            with wave.open(wav,'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(RATE);out.writeframes(pcm)
            try:
                async with asyncio.timeout(30):
                    text=await stt.transcribe_file(wav.getvalue(),filename='kadence-remote.wav',content_type='audio/wav')
                if text:
                    import re
                    tokens=text.split()
                    if words:
                        previous=words[-1].split()
                        clean=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
                        for count in range(min(16,len(previous),len(tokens)),0,-1):
                            if list(map(clean,previous[-count:]))==list(map(clean,tokens[:count])):
                                tokens=tokens[count:];break
                    if tokens:words.append(' '.join(tokens))
            except VoiceNoSpeechDetected:pass
        if not words:raise VoiceNoSpeechDetected('No speech in remote capture')
        return ' '.join(words)

    def close(self):
        self.closed=True
        if not self.ready.done():self.ready.cancel()
        self.file.close()


async def remote_turn(app, capture):
    """Reserve the existing voice owner from PTT start until playback completion."""
    from .voice_wire import process_audio_turn
    from .runtime_bridge import RuntimePresentationBridge
    body=app._body
    result=None;committed=False
    try:
        await app.tracking.stop('Tracking stopped for remote speech.')
        if getattr(app,'motion',None):await app.motion.stop()
        if app.perception:await app.perception.interrupt()
        bridge=RuntimePresentationBridge(body)
        async def state(value):
            if app._body is not body or not body.connected:raise RuntimeError('Robot disconnected.')
            await bridge.set_state(value);app.emit('activity',{'state':value,'source':'remote'})
        await state('listening')
        await capture.ready
        await state('thinking')
        async def progress(value):
            app._provider_stage=value;app.emit('provider_stage',{'stage':value})
        # A remote turn has no CoreS3 microphone socket. Robot snapshots use the
        # existing camera media command; UnitV2 continues through CameraManager.
        async def snapshot():return await app._run_media(body,'camera.snapshot')
        app._capture_in_voice=snapshot
        result=await process_audio_turn(capture.transcribe,settings=app.settings.providers,
            companion=app._companion,state_sink=state,progress_sink=progress)
        app._capture_in_voice=None
        await state('speaking')
        if app.settings.audio_output=='windows':
            app._windows_audio.start(result.pcm)
            await app._windows_audio.finish()
        else:
            app._alert_pcm=result.pcm
            await app._run_media(body,'voice.alert',preserve_tracking=True)
        if app._companion:app._companion.commit_spoken(result.transcript,result.reply)
        committed=True
        app._turn_sequence+=1;app.emit('turn',{'completed':app._turn_sequence})
    except asyncio.CancelledError:raise
    except Exception as exc:
        capture.error='Remote speech did not complete. Check the server diagnostics.'
        app._report_issue('remote_voice',exc)
        app.emit('remote_event',{'event':'audio_failed'})
    finally:
        app._capture_in_voice=None;app._alert_pcm=b'';app._windows_audio.stop()
        if app._companion and not committed:app._companion.abort_turn()
        capture.close()
        if body and body.connected:
            with contextlib.suppress(Exception):
                await RuntimePresentationBridge(body).set_state('idle')
        app.emit('activity',{'state':'idle','source':'remote'})
