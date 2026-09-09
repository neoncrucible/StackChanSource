from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Any, Callable

from .host import HostServer, Session
from .protocol import Envelope, MessageKind
from .state import Presence

_CAMERA_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_CAMERA_NUMERIC_FIELDS = frozenset({
    "stack_min_free_bytes", "internal_free", "internal_largest",
    "psram_free", "psram_largest", "pmic_enable_ok", "pmic_enable",
    "pmic_camera_ok", "pmic_camera", "expander_output_ok",
    "expander_output", "expander_config_ok", "expander_config",
    "frame_received", "expected",
})


def parse_camera_diagnostic(text: str) -> dict[str, Any] | None:
    """Extract only bounded, secret-free camera evidence from ESP-IDF logs."""
    if not isinstance(text, str):
        return None
    marker = None
    for candidate in ("CAMERA_DIAG ", "CAMERA_POWER "):
        index = text.find(candidate)
        if index >= 0:
            marker = candidate
            text = text[index + len(candidate):]
            break
    if marker is None:
        return None

    result: dict[str, Any] = {"kind": "diag" if marker.startswith("CAMERA_DIAG") else "power"}
    for item in text.split():
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key in {"stage", "failure", "err"}:
            if _CAMERA_TOKEN.fullmatch(value):
                result["stage" if key in {"stage", "failure"} else "error"] = value
            continue
        if key not in _CAMERA_NUMERIC_FIELDS:
            continue
        try:
            number = int(value, 0)
        except ValueError:
            continue
        if 0 <= number <= 0xFFFFFFFF:
            result[key] = number
    return result if len(result) > 1 else None


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

    ESP-IDF diagnostic lines are ignored except for the explicit, bounded camera
    evidence parser above. Only complete JSON protocol envelopes are dispatched
    into HostServer, preserving correlation, timeout, retirement and single-command
    ownership rules. Device-originated v1 events are also queued for the appliance
    runtime before their normal host.event acknowledgement is emitted.
    """

    def __init__(self, host: HostServer, serial_port: Any, *, port_name: str,
                 diagnostic_sink: Callable[[dict[str, Any]], None] | None = None):
        self.host = host
        self.serial_port = serial_port
        self.port_name = port_name
        self.diagnostic_sink = diagnostic_sink
        self.writer = SerialEnvelopeWriter(serial_port)
        self.session = Session(device_id=f"serial:{port_name}", hello_seen=True)
        self._reader_task: asyncio.Task[None] | None = None
        self._started = False
        self._events: asyncio.Queue[Envelope] = asyncio.Queue(maxsize=16)
        self._disconnected = asyncio.Event()
        self._disconnected.set()

    @property
    def connected(self) -> bool:
        return self._started and not self._disconnected.is_set()

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
            if (
                "PROBE21 status=ready" in text
                or "PROBE20 status=ready" in text
                or "PROBE19 status=ready" in text
                or ("BODY_HEARTBEAT" in text and "status=ok" in text)
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

        self._disconnected.clear()
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

    async def wait_disconnected(self) -> None:
        """Wait until the physical serial session exits for any reason."""
        await self._disconnected.wait()

    async def next_event(self, *, timeout: float | None = None) -> Envelope:
        """Return the next device-originated protocol event."""
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        if timeout is None:
            return await self._events.get()
        return await asyncio.wait_for(self._events.get(), timeout=timeout)

    def _queue_event(self, incoming: Envelope) -> None:
        if self._events.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._events.get_nowait()
        self._events.put_nowait(incoming)

    def _forward_diagnostic(self, text: str) -> bool:
        diagnostic = parse_camera_diagnostic(text)
        if diagnostic is None:
            return False
        if self.diagnostic_sink is not None:
            with contextlib.suppress(Exception):
                self.diagnostic_sink(diagnostic)
        return True

    async def _reader_loop(self) -> None:
        try:
            while True:
                raw = await asyncio.to_thread(self.serial_port.readline)
                text = _decode_line(raw)
                if not text:
                    continue
                if not text.startswith("{"):
                    self._forward_diagnostic(text)
                    continue
                try:
                    incoming = Envelope.from_json(text)
                except (TypeError, ValueError):
                    continue
                if incoming.kind is MessageKind.EVENT:
                    self._queue_event(incoming)
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
            self._disconnected.set()


def _decode_line(raw: bytes) -> str:
    try:
        return raw.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return ""
