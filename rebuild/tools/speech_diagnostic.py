import asyncio,time
from kcore.voice_providers import EdgeNeuralTTS
async def main():
    started=time.monotonic();stages=[]
    async def progress(stage):
        stages.append(stage);print(stage,round(time.monotonic()-started,2),flush=True)
    pcm=await EdgeNeuralTTS().synthesize_pcm('Kadence speech check. System ready.',progress_sink=progress)
    print('PCM_COMPLETE',len(pcm),round(time.monotonic()-started,2),flush=True)
    assert len(pcm)>16000 and any(pcm)
    assert 'tts_fallback' not in stages,stages
asyncio.run(main())
