from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from typing import Iterable

from .identity import KADENCE_IDENTITY
from .voice_providers import LiveVoiceProviders, VoiceProviderSettings, VoiceProviderUnavailable

UPLINK_MAGIC = b"KDV1"
REPLY_MAGIC = b"KDR1"
ERROR_MAGIC = b"KDE1"
WIRE_SAMPLE_RATE = 16000
WIRE_FRAME_MS = 60
MAX_OPUS_PACKET = 1500
MAX_PACKETS = 180
MAX_PCM_REPLY = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class VoiceWireTurn:
    sample_rate: int
    frame_ms: int
    packets: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class VoiceWireResult:
    transcript: str
    reply: str
    pcm: bytes


def _ogg_crc(page: bytes) -> int:
    crc = 0
    for value in page:
        crc ^= value << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def _ogg_page(
    packet: bytes,
    *,
    serial: int,
    sequence: int,
    granule: int,
    header_type: int,
) -> bytes:
    if not packet:
        raise ValueError("Ogg packet must not be empty")
    lacing = bytearray()
    remaining = len(packet)
    while remaining >= 255:
        lacing.append(255)
        remaining -= 255
    lacing.append(remaining)
    if len(lacing) > 255:
        raise ValueError("Ogg packet requires too many lacing values")

    header = bytearray()
    header.extend(b"OggS")
    header.append(0)
    header.append(header_type & 0xFF)
    header.extend(struct.pack("<Q", granule))
    header.extend(struct.pack("<I", serial & 0xFFFFFFFF))
    header.extend(struct.pack("<I", sequence & 0xFFFFFFFF))
    header.extend(b"\x00\x00\x00\x00")
    header.append(len(lacing))
    header.extend(lacing)

    page = header + packet
    crc = _ogg_crc(bytes(page))
    page[22:26] = struct.pack("<I", crc)
    return bytes(page)


def build_ogg_opus(
    packets: Iterable[bytes],
    *,
    sample_rate: int = WIRE_SAMPLE_RATE,
    frame_ms: int = WIRE_FRAME_MS,
) -> bytes:
    frames = tuple(bytes(packet) for packet in packets if packet)
    if not frames:
        raise ValueError("at least one Opus packet is required")
    if sample_rate != WIRE_SAMPLE_RATE or frame_ms != WIRE_FRAME_MS:
        raise ValueError("wire Opus contract is fixed at 16 kHz / 60 ms")
    if any(len(packet) > MAX_OPUS_PACKET for packet in frames):
        raise ValueError("Opus packet exceeds wire limit")

    serial = 0x4B414445  # 'KADE' - deterministic for one-file turn containers.
    opus_head = (
        b"OpusHead"
        + bytes((1, 1))
        + struct.pack("<H", 0)
        + struct.pack("<I", sample_rate)
        + struct.pack("<h", 0)
        + bytes((0,))
    )
    vendor = b"Kadence clean rebuild"
    opus_tags = b"OpusTags" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)

    pages = [
        _ogg_page(opus_head, serial=serial, sequence=0, granule=0, header_type=0x02),
        _ogg_page(opus_tags, serial=serial, sequence=1, granule=0, header_type=0x00),
    ]
    granule = 0
    granule_step = 48000 * frame_ms // 1000
    for index, packet in enumerate(frames):
        granule += granule_step
        pages.append(
            _ogg_page(
                packet,
                serial=serial,
                sequence=index + 2,
                granule=granule,
                header_type=0x04 if index == len(frames) - 1 else 0x00,
            )
        )
    return b"".join(pages)


def decode_edge_mp3_to_pcm16(mp3: bytes) -> bytes:
    if not mp3:
        raise ValueError("Edge TTS returned no MP3 bytes")
    try:
        import miniaudio
    except ImportError as exc:  # pragma: no cover - local environment dependent
        raise VoiceProviderUnavailable(
            "voice wire requires miniaudio; install the rebuild voice extra"
        ) from exc

    decoded = miniaudio.decode(
        mp3,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=WIRE_SAMPLE_RATE,
    )
    pcm = decoded.samples.tobytes()
    if not pcm or len(pcm) % 2:
        raise RuntimeError("decoded Sonia audio was not valid PCM16 mono")
    if len(pcm) > MAX_PCM_REPLY:
        raise RuntimeError("decoded Sonia reply exceeds voice wire limit")
    return pcm


async def read_wire_turn(reader: asyncio.StreamReader) -> VoiceWireTurn:
    hello = await reader.readexactly(8)
    magic, sample_rate, frame_ms = struct.unpack("!4sHH", hello)
    if magic != UPLINK_MAGIC:
        raise ValueError("invalid voice wire uplink magic")
    if sample_rate != WIRE_SAMPLE_RATE or frame_ms != WIRE_FRAME_MS:
        raise ValueError("unsupported voice wire audio contract")

    packets: list[bytes] = []
    while True:
        raw_len = await reader.readexactly(2)
        (packet_len,) = struct.unpack("!H", raw_len)
        if packet_len == 0:
            break
        if packet_len > MAX_OPUS_PACKET:
            raise ValueError("voice wire Opus packet too large")
        if len(packets) >= MAX_PACKETS:
            raise ValueError("voice wire turn exceeded packet limit")
        packets.append(await reader.readexactly(packet_len))

    if not packets:
        raise ValueError("voice wire turn contained no Opus frames")
    return VoiceWireTurn(sample_rate, frame_ms, tuple(packets))


async def process_wire_turn(
    turn: VoiceWireTurn,
    *,
    settings: VoiceProviderSettings | None = None,
) -> VoiceWireResult:
    resolved = VoiceProviderSettings.from_env() if settings is None else settings
    missing = resolved.missing_credentials()
    if missing:
        raise VoiceProviderUnavailable("missing credentials: " + ",".join(missing))
    providers = LiveVoiceProviders.from_settings(resolved)

    ogg = build_ogg_opus(
        turn.packets,
        sample_rate=turn.sample_rate,
        frame_ms=turn.frame_ms,
    )
    transcript = await providers.stt.transcribe_file(
        ogg,
        filename="kadence-turn.ogg",
        content_type="audio/ogg",
    )

    prompt = KADENCE_IDENTITY.wrap_user_text(transcript)
    reply_parts: list[str] = []
    async for chunk in providers.thinker.stream_reply(prompt):
        reply_parts.append(chunk)
    reply = "".join(reply_parts).strip()
    if not reply:
        raise RuntimeError("Thinker returned an empty reply")

    mp3_parts: list[bytes] = []
    async for chunk in providers.tts.synthesize(reply):
        mp3_parts.append(chunk)
    mp3 = b"".join(mp3_parts)
    pcm = decode_edge_mp3_to_pcm16(mp3)
    return VoiceWireResult(transcript=transcript, reply=reply, pcm=pcm)


async def send_wire_reply(writer: asyncio.StreamWriter, pcm: bytes) -> None:
    if not pcm or len(pcm) > MAX_PCM_REPLY or len(pcm) % 2:
        raise ValueError("invalid voice wire PCM reply")
    writer.write(REPLY_MAGIC + struct.pack("!I", len(pcm)) + pcm)
    await writer.drain()


async def send_wire_error(writer: asyncio.StreamWriter, message: str) -> None:
    raw = message.encode("utf-8", errors="replace")[:512]
    writer.write(ERROR_MAGIC + struct.pack("!H", len(raw)) + raw)
    await writer.drain()
