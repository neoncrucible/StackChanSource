from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from .commands import decode_body_command
from .config import RuntimeConfig
from .protocol import Envelope, MessageKind
from .state import Presence, RuntimeState
from .transport import PeerClosed, read_envelope, write_envelope


@dataclass(slots=True)
class Session:
    device_id: str | None = None
    hello_seen: bool = False


class HostServer:
    """Minimal single-endpoint host runtime.

    One physical device owns the body at a time. A second connection is
    rejected instead of being allowed to race authoritative presence state.
    """

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self.state = RuntimeState()
        self._server: asyncio.AbstractServer | None = None
        self._active_writer: asyncio.StreamWriter | None = None
        self._active_session: Session | None = None
        self._client_done = asyncio.Event()
        self._client_done.set()
        self._write_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[Envelope]] = {}
        self._retired_order: deque[str] = deque()
        self._retired: set[str] = set()
        self._retired_limit = 64

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("host is not listening")
        host, port, *_ = self._server.sockets[0].getsockname()
        return str(host), int(port)

    async def start(self, *, port: int | None = None) -> tuple[str, int]:
        if self._server is not None:
            raise RuntimeError("host is already started")
        self._server = await asyncio.start_server(
            self._handle_client,
            self.config.host,
            self.config.port if port is None else port,
            limit=64 * 1024,
        )
        return self.address

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        writer = self._active_writer
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            try:
                await asyncio.wait_for(self._client_done.wait(), timeout=1.0)
            except TimeoutError:
                pass

    async def send_body_pose(
        self,
        yaw: int,
        pitch: int,
        *,
        timeout: float = 2.0,
    ) -> Envelope:
        """Send one bounded body pose command and require a correlated ACK."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        async with self._command_lock:
            writer = self._active_writer
            session = self._active_session
            if writer is None or session is None or not session.hello_seen:
                raise RuntimeError("body endpoint is not ready")

            candidate = Envelope(
                MessageKind.COMMAND,
                "body.pose",
                {"yaw": yaw, "pitch": pitch},
            )
            safe = decode_body_command(candidate)
            command = Envelope(
                MessageKind.COMMAND,
                "body.pose",
                {"yaw": safe.yaw, "pitch": safe.pitch},
                request_id=candidate.request_id,
            )

            loop = asyncio.get_running_loop()
            pending: asyncio.Future[Envelope] = loop.create_future()
            if command.request_id in self._pending:
                raise RuntimeError("duplicate pending request id")
            self._pending[command.request_id] = pending
            try:
                await self._send(writer, command)
                response = await asyncio.wait_for(pending, timeout=timeout)
            except TimeoutError:
                self._retire_request(command.request_id)
                raise
            except asyncio.CancelledError:
                self._retire_request(command.request_id)
                raise
            finally:
                self._pending.pop(command.request_id, None)

            if response.kind is not MessageKind.ACK:
                raise RuntimeError(f"body command expected ACK, got {response.kind.value}")
            if response.name != command.name:
                raise RuntimeError(
                    f"body command ACK name mismatch: expected {command.name}, got {response.name}"
                )
            if response.payload.get("ok") is not True:
                raise RuntimeError("body command was not acknowledged as successful")
            return response

    async def send_presentation_state(
        self,
        state: str,
        *,
        timeout: float = 2.0,
    ) -> Envelope:
        """Send one provider-independent presentation state over the v1 protocol."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        allowed = {
            "idle",
            "attentive",
            "listening",
            "thinking",
            "speaking",
            "tool-working",
            "offline",
            "degraded",
            "fault",
            "recovery",
        }
        if state not in allowed:
            raise ValueError(f"unsupported presentation state: {state}")

        writer = self._active_writer
        session = self._active_session
        if writer is None or session is None or not session.hello_seen:
            raise RuntimeError("body endpoint is not ready")

        command = Envelope(
            MessageKind.COMMAND,
            "presentation.state",
            {"state": state},
        )
        loop = asyncio.get_running_loop()
        pending: asyncio.Future[Envelope] = loop.create_future()
        if command.request_id in self._pending:
            raise RuntimeError("duplicate pending request id")
        self._pending[command.request_id] = pending
        try:
            await self._send(writer, command)
            response = await asyncio.wait_for(pending, timeout=timeout)
        except TimeoutError:
            self._retire_request(command.request_id)
            raise
        except asyncio.CancelledError:
            self._retire_request(command.request_id)
            raise
        finally:
            self._pending.pop(command.request_id, None)

        if response.kind is not MessageKind.ACK:
            raise RuntimeError(
                f"presentation command expected ACK, got {response.kind.value}"
            )
        if response.name != command.name:
            raise RuntimeError(
                "presentation command ACK name mismatch: "
                f"expected {command.name}, got {response.name}"
            )
        if response.payload.get("ok") is not True:
            raise RuntimeError("presentation state was not acknowledged")
        if response.payload.get("state") != state:
            raise RuntimeError("presentation state ACK did not confirm requested state")
        return response

    async def send_voice_audio_check(
        self,
        *,
        timeout: float = 8.0,
    ) -> Envelope:
        """Run one exclusive device microphone-to-speaker ownership check."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        async with self._command_lock:
            writer = self._active_writer
            session = self._active_session
            if writer is None or session is None or not session.hello_seen:
                raise RuntimeError("body endpoint is not ready")

            command = Envelope(MessageKind.COMMAND, "voice.audio-check", {})
            loop = asyncio.get_running_loop()
            pending: asyncio.Future[Envelope] = loop.create_future()
            if command.request_id in self._pending:
                raise RuntimeError("duplicate pending request id")
            self._pending[command.request_id] = pending
            try:
                await self._send(writer, command)
                response = await asyncio.wait_for(pending, timeout=timeout)
            except TimeoutError:
                self._retire_request(command.request_id)
                raise
            except asyncio.CancelledError:
                self._retire_request(command.request_id)
                raise
            finally:
                self._pending.pop(command.request_id, None)

            if response.kind is not MessageKind.ACK:
                raise RuntimeError(
                    f"voice audio check expected ACK, got {response.kind.value}"
                )
            if response.name != command.name:
                raise RuntimeError(
                    "voice audio check ACK name mismatch: "
                    f"expected {command.name}, got {response.name}"
                )
            required = ("ok", "capture", "playback", "handoff", "torque_released")
            missing = [key for key in required if response.payload.get(key) is not True]
            if missing:
                raise RuntimeError(
                    "voice audio check proof missing: " + ",".join(missing)
                )
            return response

    async def _send(self, writer: asyncio.StreamWriter, envelope: Envelope) -> None:
        async with self._write_lock:
            await write_envelope(writer, envelope)

    def _retire_request(self, request_id: str) -> None:
        if request_id in self._retired:
            return
        if len(self._retired_order) >= self._retired_limit:
            oldest = self._retired_order.popleft()
            self._retired.discard(oldest)
        self._retired_order.append(request_id)
        self._retired.add(request_id)

    def _resolve_pending(self, incoming: Envelope) -> None:
        pending = self._pending.get(incoming.request_id)
        if pending is None:
            if incoming.request_id in self._retired:
                self._retired.discard(incoming.request_id)
                return
            raise ValueError(f"unexpected correlated response: {incoming.request_id}")
        if pending.done():
            raise ValueError(f"duplicate correlated response: {incoming.request_id}")
        pending.set_result(incoming)

    def _fail_pending(self, exc: Exception) -> None:
        for pending in tuple(self._pending.values()):
            if not pending.done():
                pending.set_exception(exc)
        self._pending.clear()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._active_writer is not None:
            try:
                await self._send(
                    writer,
                    Envelope(
                        MessageKind.ERROR,
                        "host.busy",
                        {"message": "physical endpoint already connected"},
                    ),
                )
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
            return

        self._active_writer = writer
        self._client_done.clear()
        session = Session()
        self._active_session = session
        try:
            while True:
                incoming = await read_envelope(reader)
                outgoing = self._dispatch(session, incoming)
                if outgoing is not None:
                    await self._send(writer, outgoing)
        except PeerClosed:
            pass
        except Exception as exc:
            try:
                await self._send(
                    writer,
                    Envelope(MessageKind.ERROR, "host.error", {"message": str(exc)}),
                )
            except Exception:
                pass
        finally:
            self._fail_pending(PeerClosed("body endpoint disconnected"))
            self._retired_order.clear()
            self._retired.clear()
            if self.state.presence not in {Presence.OFFLINE, Presence.FAULT}:
                self.state.transition(Presence.OFFLINE)
            self._active_session = None
            self._active_writer = None
            self._client_done.set()
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    def _dispatch(self, session: Session, incoming: Envelope) -> Envelope | None:
        if incoming.kind is MessageKind.HELLO:
            if session.hello_seen:
                raise ValueError("duplicate hello")
            device_id = incoming.payload.get("device_id")
            if not isinstance(device_id, str) or not device_id.strip():
                raise ValueError("hello requires non-empty device_id")
            session.device_id = device_id.strip()
            session.hello_seen = True
            if self.state.presence in {Presence.BOOTING, Presence.OFFLINE}:
                self.state.transition(Presence.IDLE)
            return Envelope(
                MessageKind.READY,
                "host.ready",
                {
                    "device_id": session.device_id,
                    "presence": self.state.presence.value,
                    "sequence": self.state.sequence,
                },
                request_id=incoming.request_id,
            )

        if not session.hello_seen:
            raise ValueError("hello required before other messages")

        if incoming.kind is MessageKind.ACK:
            self._resolve_pending(incoming)
            return None

        if incoming.kind is MessageKind.HEARTBEAT:
            return Envelope(
                MessageKind.ACK,
                "host.heartbeat",
                {"presence": self.state.presence.value},
                request_id=incoming.request_id,
            )

        if incoming.kind is MessageKind.EVENT:
            return Envelope(
                MessageKind.ACK,
                "host.event",
                {"accepted": incoming.name},
                request_id=incoming.request_id,
            )

        raise ValueError(f"unsupported inbound message kind: {incoming.kind.value}")
