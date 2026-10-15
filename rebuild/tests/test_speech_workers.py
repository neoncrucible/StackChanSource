"""Preloaded real processes still stream, cancel and exit without orphaning."""
import asyncio
import sys
from unittest.mock import patch

import pytest

from kcore import speech_output
from kcore.speech_workers import SpeechWorkers
from kcore.voice_providers import VoiceProviderUnavailable


def test_warm_children_are_ready_before_text_and_are_single_use():
    async def run():
        spawned=[]
        original=asyncio.create_subprocess_exec
        async def spawn(*args,**kwargs):
            child=await original(*args,**kwargs)
            spawned.append(child)
            return child
        script="""
import json,sys
print('{"ready":true}',flush=True)
sys.stdin.read()
sys.stdout.buffer.write(b'{"pcm_bytes":4}\\n\\1\\0\\2\\0{"done":true}\\n')
sys.stdout.flush()
"""
        command=[sys.executable,'-c',script]
        with patch.object(speech_output,'child_command',return_value=command), patch.object(asyncio,'create_subprocess_exec',side_effect=spawn):
            workers=speech_output.warm_workers()
            try:
                ready=await asyncio.wait_for(asyncio.gather(*workers.waiting),5)
                assert len(ready)==2 and all(p.returncode is None for p in ready)
                heard=[]
                async def sink(chunk): heard.append(chunk)
                pcm=await speech_output._render(command,b'one utterance',timeout=3,pcm_sink=sink)
                assert pcm==b'\1\0\2\0'==b''.join(heard)
                assert ready[0].returncode==0
                pcm=await speech_output._render(command,b'a different utterance',timeout=3,pcm_sink=sink)
                assert ready[1].returncode==0
            finally:
                await speech_output.close_workers(workers)
            assert all(p.returncode is not None for p in spawned)
            assert speech_output._workers is None
    asyncio.run(run())


def test_shutdown_reaps_children_while_they_are_loading():
    async def run():
        spawned=[]; original=asyncio.create_subprocess_exec
        async def spawn(*args,**kwargs):
            child=await original(*args,**kwargs); spawned.append(child); return child
        with patch.object(asyncio,'create_subprocess_exec',side_effect=spawn):
            workers=SpeechWorkers([sys.executable,'-c','import time; time.sleep(60)'],speech_output.child_environment())
            await asyncio.sleep(.05)
            await asyncio.wait_for(workers.close(),3)
        assert spawned and all(p.returncode is not None for p in spawned)
        assert not [t for t in asyncio.all_tasks() if t.get_name()=='kadence-speech-warmup']
    asyncio.run(run())


def test_actual_speech_child_preloads_decoder_without_provider_or_audio():
    async def run():
        workers=SpeechWorkers(speech_output.child_command(),speech_output.child_environment(),count=1)
        try:
            process=await asyncio.wait_for(asyncio.shield(workers.waiting[0]),12)
            assert process.returncode is None
            # No text has been supplied and no audio device or provider was used.
        finally:
            await workers.close()
        assert process.returncode is not None
    asyncio.run(run())


def test_failed_warm_child_reports_provider_failure_and_reaps():
    async def run():
        workers=SpeechWorkers([sys.executable,'-c','print("broken")'],speech_output.child_environment(),count=1)
        try:
            with pytest.raises(VoiceProviderUnavailable): await workers.take()
        finally: await workers.close()
    asyncio.run(run())
