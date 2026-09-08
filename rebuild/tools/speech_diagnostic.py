"""Synthetic RC1 speech path in RC2's frozen desktop environment."""
import asyncio, contextlib, importlib.metadata, json, os, subprocess, sys, tempfile, time
from kcore.voice_providers import EdgeNeuralTTS, LiveVoiceProviders, VoiceProviderSettings
import kcore.voice_wire as wire
from kcore.desktop_worker import DesktopController

out=sys.stdout
def log(*args): print(*args,file=out,flush=True)
async def run():
    started=time.monotonic()
    def stage(*args): log(*args,round(time.monotonic()-started,2))
    original=EdgeNeuralTTS.synthesize
    async def instrumented(self,text):
        stage('NETWORK_START'); first=True
        async for data in original(self,text):
            if first: stage('FIRST_AUDIO'); first=False
            yield data
        stage('NETWORK_COMPLETE')
    EdgeNeuralTTS.synthesize=instrumented
    decode=wire.decode_edge_mp3_to_pcm16
    def conversion(data):
        stage('DECODE_START',len(data))
        result=decode(data)
        stage('DECODE_DONE',len(result))
        return result
    wire.decode_edge_mp3_to_pcm16=conversion
    controller=DesktopController(lambda *_:None)
    await controller.start()
    try:
        providers=LiveVoiceProviders.from_settings(VoiceProviderSettings(None,None))
        pcm=await asyncio.wait_for(wire._synthesize_reply(providers,'Kadence audio diagnostic. Ready.'),30)
        stage('PCM_COMPLETE',len(pcm))
    except Exception as e: stage('FAILURE',type(e).__name__,str(e)[:240])
    finally: await controller.close()

if __name__=='__main__':
    if '--child' in sys.argv:
        with open(os.devnull,'w') as discard,contextlib.redirect_stdout(discard),contextlib.redirect_stderr(discard):
            asyncio.run(run())
    else:
        log('FROZEN',getattr(sys,'frozen',False))
        args=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-u',__file__]
        with tempfile.TemporaryDirectory() as tmp:
            try: subprocess.run([*args,'--child'],timeout=38,check=True,env={**os.environ,'KADENCE_DATA_DIR':tmp})
            except subprocess.TimeoutExpired: log('HARD_TIMEOUT')
