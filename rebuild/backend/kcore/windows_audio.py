"""Cancellable speech on the Windows default device, including Bluetooth."""
import asyncio
import os
import tempfile
import time
import threading
from collections import deque
from pathlib import Path
from .voice_providers import pcm16_mono_to_wav

MAX_PCM = 4 * 1024 * 1024
PREBUFFER_BYTES = 6400  # 200 ms at 16 kHz / mono PCM16.


class PlaybackBuffer:
    """Bounded queue; the audio callback never waits for the network or decoder."""
    def __init__(self):
        self._lock = threading.Lock()
        self._chunks = deque()
        self.pending = 0
        self.total = 0
        self.ends = 0.0
        self.underruns = 0
        self.complete = False

    def feed(self, pcm):
        if not pcm or len(pcm) % 2:
            raise ValueError("Invalid streaming PCM")
        with self._lock:
            if self.complete or self.total + len(pcm) > MAX_PCM:
                raise ValueError("Streaming PCM exceeds limit or is closed")
            self._chunks.append(bytes(pcm))
            self.pending += len(pcm)
            self.total += len(pcm)

    def read(self, frames):
        count = frames * 2
        result = bytearray()
        with self._lock:
            while self._chunks and len(result) < count:
                chunk = self._chunks.popleft()
                take = min(count - len(result), len(chunk))
                result.extend(chunk[:take])
                if take < len(chunk):
                    self._chunks.appendleft(chunk[take:])
            self.pending -= len(result)
            if result:
                # Include a short device drain guard after the last samples are
                # handed to Windows. This is not Bluetooth acoustic telemetry.
                self.ends = time.monotonic() + len(result) / 32000 + .15
            if len(result) < count and not self.complete:
                self.underruns += 1
        return bytes(result) + bytes(count - len(result))

    def remaining_bytes(self):
        with self._lock:
            drain = max(0.0, self.ends - time.monotonic())
            return self.pending + int(drain * 16000 + .999) * 2

    def callback(self):
        frames = yield b""
        while True:
            frames = yield self.read(frames)

class WindowsAudio:
    def __init__(self):
        self._path = None
        self._ends = 0.0
        self._device = None
        self._buffer = None

    @property
    def streaming_started(self):
        return self._device is not None

    def feed(self, pcm):
        if os.name != "nt":
            raise RuntimeError("Windows speech output requires Windows.")
        if self._buffer is None:
            self.stop()
            self._buffer = PlaybackBuffer()
        self._buffer.feed(pcm)
        if self._device is None and self._buffer.pending >= PREBUFFER_BYTES:
            self._start_stream()

    def _start_stream(self):
        import miniaudio
        # Explicit backends prevent silent success via miniaudio's null device.
        self._device = miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1, sample_rate=16000, buffersize_msec=50,
            backends=[miniaudio.Backend.WASAPI, miniaudio.Backend.WINMM], app_name="Kadence")
        callback = self._buffer.callback()
        next(callback)
        try:
            self._device.start(callback)
        except BaseException:
            self.stop()
            raise

    def end_stream(self):
        if self._buffer is None or not self._buffer.total:
            raise RuntimeError("Streaming speech returned no samples")
        self._buffer.complete = True
        if self._device is None:
            self._start_stream()

    def remaining_pcm_bytes(self):
        return min(MAX_PCM, max(2, self._buffer.remaining_bytes())) if self._buffer else 2

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
            buffer = self._buffer
            if buffer is not None:
                deadline = time.monotonic() + buffer.total / 32000 + 5
                while self._buffer is buffer and (not buffer.complete or buffer.remaining_bytes()):
                    if time.monotonic() > deadline:
                        raise TimeoutError("Windows audio did not drain")
                    await asyncio.sleep(.02)
            while time.monotonic() < self._ends:
                await asyncio.sleep(0.05)
        finally:
            self.stop()

    def stop(self):
        device, self._device = self._device, None
        if device is not None:
            device.close()
        self._buffer = None
        if self._path is None:
            return
        import winsound
        winsound.PlaySound(None, 0)
        self._path.unlink(missing_ok=True)
        self._path = None
        self._ends = 0.0
