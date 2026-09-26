"""Frame-by-frame MP3 decoding, confined to the disposable speech child.

The generic file decoder reads ahead 64 KiB (about 11 seconds of Edge's MP3).
An explicit MP3 packet parser avoids that delay and preserves the codec's bit
reservoir and resampler state across arbitrary network chunk boundaries.
"""
from __future__ import annotations

MAX_AUDIO = 4 * 1024 * 1024


class Mp3Decoder:
    def __init__(self):
        import av
        self._codec = av.CodecContext.create("mp3", "r")
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        self._encoded = 0
        self._decoded = 0
        self._header = bytearray()
        self._header_done = False
        self._finished = False

    def _pcm(self, frames):
        for frame in frames:
            # Planes can include alignment padding; emit only mono samples.
            pcm = bytes(frame.planes[0])[:frame.samples * 2]
            self._decoded += len(pcm)
            if self._decoded > MAX_AUDIO:
                raise ValueError("Decoded speech exceeds limit")
            if pcm:
                yield pcm

    def _decode(self, packets):
        for packet in packets:
            for frame in self._codec.decode(packet):
                yield from self._pcm(self._resampler.resample(frame))

    def feed(self, data):
        if self._finished:
            raise ValueError("Speech stream already finished")
        self._encoded += len(data)
        if self._encoded > MAX_AUDIO:
            raise ValueError("Encoded speech exceeds limit")
        if not self._header_done:
            self._header.extend(data)
            if len(self._header) < 10:
                return
            skip = 0
            if self._header[:3] == b"ID3":
                size = self._header[6:10]
                if any(value & 0x80 for value in size):
                    raise ValueError("Invalid MP3 metadata")
                skip = 10 + sum(value << shift for value, shift in zip(size, (21, 14, 7, 0)))
                if self._header[5] & 0x10:
                    skip += 10
                if skip > MAX_AUDIO:
                    raise ValueError("MP3 metadata exceeds limit")
                if len(self._header) < skip:
                    return
            data = bytes(self._header[skip:])
            self._header.clear()
            self._header_done = True
        if data:
            yield from self._decode(self._codec.parse(data))

    def finish(self):
        if self._finished:
            raise ValueError("Speech stream already finished")
        self._finished = True
        yield from self._decode(self._codec.parse(b""))
        for frame in self._codec.decode(None):
            yield from self._pcm(self._resampler.resample(frame))
        yield from self._pcm(self._resampler.resample(None))
        if not self._decoded:
            raise ValueError("Empty speech stream")


def decoder_check(raw):
    """Offline exercise of the real decoder in the shipped executable."""
    import hashlib
    decoder = Mp3Decoder()
    total = 0
    first = None
    digest = hashlib.sha256()
    for offset in range(0, len(raw), 576):
        for pcm in decoder.feed(raw[offset:offset + 576]):
            if first is None:
                first = min(offset + 576, len(raw))
            total += len(pcm)
            digest.update(pcm)
    for pcm in decoder.finish():
        total += len(pcm)
        digest.update(pcm)
    return {"pcm_bytes": total, "first_encoded_bytes": first,
            "before_eof": first is not None and first < len(raw), "sha256": digest.hexdigest()}
