"""Real child lifecycle checks plus Windows' installed speech engine."""
import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

from kcore import speech_output as speech
from kcore.voice_providers import VoiceProviderUnavailable


class SpeechOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_pcm_validation_and_next_render(self):
        invalid = ["0", "3", str(speech.MAX_PCM + 2), "true"]
        for size in invalid:
            with self.subTest(size=size), self.assertRaises(VoiceProviderUnavailable):
                await speech._render([sys.executable, "-c",
                    f"import sys; sys.stdin.read(); print('{{\"pcm_bytes\":{size}}}')"], b"fixture", timeout=2)
        pcm = await speech._render([sys.executable, "-c",
            "import sys;sys.stdin.read();sys.stdout.buffer.write(b'{\"pcm_bytes\":4}\\n\\x01\\x00\\x02\\x00')"],
            b"fixture", timeout=2)
        self.assertEqual(pcm, b"\x01\0\x02\0")

    async def test_timeout_kills_and_reaps_a_child_that_never_returns(self):
        spawned=[]; original=asyncio.create_subprocess_exec
        async def track(*args, **kwargs):
            child=await original(*args, **kwargs); spawned.append(child); return child
        with patch.object(speech.asyncio, "create_subprocess_exec", side_effect=track):
            started=time.monotonic()
            with self.assertRaises(TimeoutError):
                await speech._render([sys.executable, "-c", "import time;time.sleep(60)"], b"fixture", timeout=.15)
        self.assertLess(time.monotonic()-started, 4)
        self.assertIsNotNone(spawned[0].returncode)

    async def test_cancel_reaps_child_and_does_not_speak_fallback(self):
        spawned=[]; entered=asyncio.Event(); original=asyncio.create_subprocess_exec
        async def track(*args, **kwargs):
            child=await original(*args, **kwargs); spawned.append(child); entered.set(); return child
        with patch.object(speech.asyncio, "create_subprocess_exec", side_effect=track):
            task=asyncio.create_task(speech._render([sys.executable, "-c", "import time;time.sleep(60)"], b"fixture", timeout=30))
            await asyncio.wait_for(entered.wait(), 3); await asyncio.sleep(.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertIsNotNone(spawned[0].returncode)
        with patch.object(speech, "_render", AsyncMock(side_effect=asyncio.CancelledError)), patch.object(speech, "synthesize_local", AsyncMock()) as local:
            with self.assertRaises(asyncio.CancelledError):
                await speech.synthesize_pcm("fixture", voice="en-GB-SoniaNeural", rate="+0%")
            local.assert_not_awaited()

    async def test_stalled_sonia_preserves_reply_for_local_voice(self):
        stages=[]
        async def progress(stage): stages.append(stage)
        with patch.object(speech, "_render", AsyncMock(side_effect=TimeoutError)), patch.object(speech, "synthesize_local", AsyncMock(return_value=b"\1\0")) as local, patch.object(speech.os, "name", "nt"):
            self.assertEqual(await speech.synthesize_pcm("The answer is ready.", voice="en-GB-SoniaNeural", rate="+0%", progress_sink=progress),b"\1\0")
            local.assert_awaited_once_with("The answer is ready.", progress_sink=progress)
        self.assertEqual(stages,["tts_fallback","tts_ready"])

    @unittest.skipUnless(os.name=="nt", "Installed Windows voice")
    async def test_windows_voice_produces_non_silent_pcm_without_an_audio_device(self):
        stages=[]
        async def progress(stage): stages.append(stage)
        try:
            pcm=await speech.synthesize_local("Kadence local speech check. Café. Ready.", progress_sink=progress)
        except TimeoutError:
            self.fail("Local speech deadline at " + (stages[-1] if stages else "process_start"))
        self.assertGreater(len(pcm), 16000)
        self.assertLess(len(pcm), speech.MAX_PCM)
        self.assertEqual(len(pcm)%2, 0)
        self.assertTrue(any(pcm))


if __name__ == "__main__": unittest.main()
