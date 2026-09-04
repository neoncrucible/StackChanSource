from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from .host import HostServer, Session
from .protocol import Envelope
from .state import Presence


class SerialEnvelopeWriter:
    """Asyncio-writer-shaped adapter over a pyserial-compatible object."""

    def __init__(self, serial_port: Any):
        self.serial_port = serial_port
        self._pending = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise ConnectionError("serial endpoint is closed")
        self._pending.extend(data)

    async def drain(self) -> None:
        if not self._pending:
            return
        raw = bytes(self._pending)
        self._pending.clear()
        await asyncio.to_thread(self.serial_port.write, raw)
        await asyncio.to_thread(self.serial_port.flush)

    def close(self) -> None:
        self._closed = True
        with contextlib.suppress(Exception):
            self.serial_port.close()

    async def wait_closed(self) -> None:
        return None


class SerialBodySession:
    """Bind one trusted serial body endpoint to the existing HostServer lifecycle.

    ESP-IDF diagnostic lines are ignored. Only complete JSON protocol envelopes
    are dispatched into HostServer, preserving its existing correlation,
    timeout, retirement and single-command ownership rules.
    """

    def __init__(self, host: HostServer, serial_port: Any, *, port_name: str):
        self.host = host
        self.serial_port = serial_port
        self.port_name = port_name
        self.writer = SerialEnvelopeWriter(serial_port)
        self.session = Session(device_id=f"serial:{port_name}", hello_seen=True)
        self._reader_task: asyncio.Task[None] | None = None
        self._started = False

    async def start(self, *, ready_timeout: float = 30.0) -> None:
        if ready_timeout <= 0:
            raise ValueError("ready_timeout must be positive")
        if self._started:
            raise RuntimeError("serial body session is already started")
        if self.host._active_writer is not None:
            raise RuntimeError("body endpoint is already connected")

        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            raw = await asyncio.to_thread(self.serial_port.readline)
            text = _decode_line(raw)
            if not text:
                continue
            if "PROBE19 status=ready" in text or (
                "BODY_HEARTBEAT" in text and "status=ok" in text
            ):
                break
        else:
            raise TimeoutError("serial body did not reach transport-ready state")

        await asyncio.to_thread(self.serial_port.reset_input_buffer)
        self.host._active_writer = self.writer
        self.host._active_session = self.session
        self.host._client_done.clear()
        if self.host.state.presence in {Presence.BOOTING, Presence.OFFLINE}:
            self.host.state.transition(Presence.IDLE)

        self._started = True
        self._reader_task = asyncio.create_task(
            self._reader_loop(), name=f"serial-body-{self.port_name}"
        )

    async def close(self) -> None:
        task = self._reader_task
        self.writer.close()
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                await task
        self._reader_task = None

    async def _reader_loop(self) -> None:
        try:
            while True:
                raw = await asyncio.to_thread(self.serial_port.readline)
                text = _decode_line(raw)
                if not text or not text.startswith("{"):
                    continue
                try:
                    incoming = Envelope.from_json(text)
                except (TypeError, ValueError):
                    continue
                outgoing = self.host._dispatch(self.session, incoming)
                if outgoing is not None:
                    await self.host._send(self.writer, outgoing)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.host._fail_pending(ConnectionError(f"serial body failed: {exc}"))
        finally:
            self.host._fail_pending(ConnectionError("serial body endpoint disconnected"))
            self.host._retired_order.clear()
            self.host._retired.clear()
            if self.host.state.presence not in {Presence.OFFLINE, Presence.FAULT}:
                self.host.state.transition(Presence.OFFLINE)
            if self.host._active_writer is self.writer:
                self.host._active_writer = None
                self.host._active_session = None
            self.host._client_done.set()
            self._started = False


def _decode_line(raw: bytes) -> str:
    try:
        return raw.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return ""
