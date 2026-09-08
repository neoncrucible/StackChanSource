"""Synthetic, credential-free Windows speech path investigation."""
import asyncio, importlib.metadata, subprocess, sys, time
from kcore.voice_providers import EdgeNeuralTTS
from kcore.voice_wire import decode_edge_mp3_to_pcm16

async def run():
    t=time.monotonic(); parts=[]
    print('START',flush=True)
    try:
        async with asyncio.timeout(18):
            async for chunk in EdgeNeuralTTS().synthesize('Kadence audio diagnostic. Ready.'):
                if not parts: print('FIRST_AUDIO',round(time.monotonic()-t,2),flush=True)
                parts.append(chunk)
        print('NETWORK_COMPLETE',sum(map(len,parts)),round(time.monotonic()-t,2),flush=True)
        pcm=await asyncio.to_thread(decode_edge_mp3_to_pcm16,b''.join(parts))
        print('PCM_COMPLETE',len(pcm),round(time.monotonic()-t,2),flush=True)
    except Exception as e:
        print('FAILURE',type(e).__name__,str(e)[:240],round(time.monotonic()-t,2),flush=True)

if __name__=='__main__':
    if '--child' in sys.argv: asyncio.run(run())
    else:
        for package in ('edge-tts','miniaudio','aiohttp'): print(package,importlib.metadata.version(package),flush=True)
        try: subprocess.run([sys.executable,'-u',__file__,'--child'],timeout=35,check=True)
        except subprocess.TimeoutExpired: print('HARD_TIMEOUT',flush=True)
