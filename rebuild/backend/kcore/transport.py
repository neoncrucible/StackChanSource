from __future__ import annotations

import asyncio

from .protocol import Envelope

MAX_FRAME_BYTES = 64 * 1024


class PeerClosed(ConnectionError):
    """Raised when a peer closes a framed transport cleanly."""


async def read_envelope(reader: asyncio.StreamReader) -> Envelope:
    raw = await reader.readline()
    if not raw:
        raise PeerClosed("peer closed connection")
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError("protocol frame exceeds 64 KiB")
    if not raw.endswith(b"\n"):
        raise ValueError("protocol frame is not newline terminated")
    try:
        text = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("protocol frame is not valid UTF-8") from exc
    return Envelope.from_json(text)


async def write_envelope(writer: asyncio.StreamWriter, envelope: Envelope) -> None:
    raw = envelope.to_json().encode("utf-8") + b"\n"
    if len(raw) > MAX_FRAME_BYTES:
        raise ValueError("protocol frame exceeds 64 KiB")
    writer.write(raw)
    await writer.drain()
