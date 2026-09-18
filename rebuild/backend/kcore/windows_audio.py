"""Cancellable speech on the Windows default device, including Bluetooth."""
import asyncio
import os
import tempfile
import time
from pathlib import Path
from .voice_providers import pcm16_mono_to_wav

class WindowsAudio:
    def __init__(self):
        self._path = None
        self._ends = 0.0

    def start(self, pcm):
        if os.name != "nt":
            raise RuntimeError("Windows speech output requires Windows.")
        import winsound
        self.stop()
        fd, name = tempfile.mkstemp(prefix="kadence-speech-", suffix=".wav")
        self._path = Path(name)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(pcm16_mono_to_wav(pcm, 16000))
            winsound.PlaySound(name, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            self._ends = time.monotonic() + len(pcm) / 32000
        except BaseException:
            self.stop()
            raise

    async def finish(self):
        try:
            while time.monotonic() < self._ends:
                await asyncio.sleep(0.05)
        finally:
            self.stop()

    def stop(self):
        if self._path is None:
            return
        import winsound
        winsound.PlaySound(None, 0)
        self._path.unlink(missing_ok=True)
        self._path = None
        self._ends = 0.0
