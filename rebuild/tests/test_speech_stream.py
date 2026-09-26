"""Real codec/child tests; no cloud service or physical sound device required."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from kcore.speech_stream import Mp3Decoder, decoder_check
from kcore import speech_output
from kcore.voice_providers import VoiceProviderUnavailable
from kcore.windows_audio import PlaybackBuffer, WindowsAudio

FIXTURE = Path(__file__).parent / "fixtures" / "stream-tone.mp3"


class DecoderTests(unittest.TestCase):
    def test_first_samples_do_not_wait_for_eof_and_fragmentation_does_not_change_audio(self):
        raw = FIXTURE.read_bytes()
        expected = decoder_check(raw)
        self.assertTrue(expected["before_eof"])
        self.assertLessEqual(expected["first_encoded_bytes"], 1152)
        self.assertEqual(expected["pcm_bytes"], 129792)
        for size in (1, 7, 576, 8192):
            with self.subTest(size=size):
                decoder = Mp3Decoder()
                chunks = []
                for offset in range(0, len(raw), size):
                    chunks.extend(decoder.feed(raw[offset:offset + size]))
                chunks.extend(decoder.finish())
                self.assertEqual(hashlib.sha256(b"".join(chunks)).hexdigest(), expected["sha256"])

    def test_buffer_preserves_samples_and_pads_temporary_underrun(self):
        buffer = PlaybackBuffer()
        buffer.feed(b"\1\0\2\0")
        buffer.feed(b"\3\0\4\0")
        self.assertEqual(buffer.read(3), b"\1\0\2\0\3\0")
        self.assertEqual(buffer.read(3), b"\4\0\0\0\0\0")
        self.assertEqual(buffer.underruns, 1)
        buffer.feed(b"\5\0\6\0")
        buffer.complete = True
        self.assertEqual(buffer.read(2), b"\5\0\6\0")
        self.assertEqual(buffer.pending, 0)
        with self.assertRaises(ValueError): buffer.feed(b"\7\0")


class ChildStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_delivers_audio_before_provider_can_finish(self):
        with tempfile.TemporaryDirectory() as root:
            release = Path(root) / "release"
            # The synthetic provider refuses to return the remaining MP3 until
            # the real parent has received PCM. Whole-file buffering deadlocks.
            script = '''
import asyncio, sys
from pathlib import Path
from kcore.voice_providers import EdgeNeuralTTS
from kcore.speech_child import main
async def fixture(self, text):
    raw = Path(sys.argv[1]).read_bytes()
    yield raw[:4096]
    async with asyncio.timeout(5):
        while not Path(sys.argv[2]).exists(): await asyncio.sleep(.01)
    yield raw[4096:]
EdgeNeuralTTS.synthesize = fixture
raise SystemExit(main())
'''
            received = []
            async def sink(pcm):
                received.append(pcm)
                release.touch()
            pcm = await speech_output._render([sys.executable, "-c", script, str(FIXTURE), str(release)],
                json.dumps({"text": "Fixture", "voice": "en-GB-SoniaNeural", "rate": "+0%", "stream": True}).encode(),
                timeout=10, pcm_sink=sink)
            self.assertEqual(pcm, b"".join(received))
            self.assertEqual(len(pcm), 129792)

    async def test_midstream_failure_is_not_replayed_by_fallback(self):
        received = []
        async def sink(pcm): received.append(pcm)
        async def fail(*args, pcm_sink, **kwargs):
            await pcm_sink(b"\1\0")
            raise TimeoutError()
        with patch.object(speech_output, "_render", side_effect=fail), patch.object(speech_output, "synthesize_local", AsyncMock()) as local:
            with self.assertRaises(TimeoutError):
                await speech_output.synthesize_pcm("Already partly heard.", voice="en-GB-SoniaNeural", rate="+0%", pcm_sink=sink)
            local.assert_not_awaited()
        self.assertEqual(received, [b"\1\0"])

    async def test_stream_requires_successful_completion_not_just_some_samples(self):
        for suffix in ("", 'print(\'{"done":true}\');sys.exit(2)', 'print(\'{"done":true}\');print("extra")'):
            with self.subTest(suffix=suffix):
                script = 'import sys;sys.stdin.read();sys.stdout.buffer.write(b\'{"pcm_bytes":2}\\n\\1\\0\');sys.stdout.flush();' + suffix
                with self.assertRaises(VoiceProviderUnavailable):
                    await speech_output._render([sys.executable, "-c", script], b"x", timeout=3, pcm_sink=AsyncMock())

    async def test_cancel_after_first_samples_reaps_child(self):
        entered = asyncio.Event(); children = []
        original = asyncio.create_subprocess_exec
        async def spawn(*args, **kwargs):
            child = await original(*args, **kwargs); children.append(child); return child
        async def sink(pcm): entered.set()
        script = 'import sys,time;sys.stdin.read();sys.stdout.buffer.write(b\'{"pcm_bytes":2}\\n\\1\\0\');sys.stdout.flush();time.sleep(60)'
        with patch.object(speech_output.asyncio, "create_subprocess_exec", side_effect=spawn):
            task = asyncio.create_task(speech_output._render([sys.executable, "-c", script], b"x", timeout=30, pcm_sink=sink))
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertIsNotNone(children[0].returncode)

    async def test_windows_cancel_while_draining_does_not_race_buffer_removal(self):
        audio = WindowsAudio()
        audio._buffer = PlaybackBuffer()
        audio._buffer.feed(b"\1\0" * 160)
        audio._buffer.complete = True
        task = asyncio.create_task(audio.finish())
        await asyncio.sleep(0)
        audio.stop()
        await asyncio.wait_for(task, 1)


if __name__ == "__main__": unittest.main()
