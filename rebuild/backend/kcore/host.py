from __future__ import annotations

import asyncio
from dataclasses import dataclass

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
        self._client_done = asyncio.Event()
        self._client_done.set()

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

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._active_writer is not None:
            try:
                await write_envelope(
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
        try:
            while True:
                incoming = await read_envelope(reader)
                outgoing = self._dispatch(session, incoming)
                await write_envelope(writer, outgoing)
        except PeerClosed:
            pass
        except Exception as exc:
            try:
                await write_envelope(
                    writer,
                    Envelope(MessageKind.ERROR, "host.error", {"message": str(exc)}),
                )
            except Exception:
                pass
        finally:
            if self.state.presence not in {Presence.OFFLINE, Presence.FAULT}:
                self.state.transition(Presence.OFFLINE)
            self._active_writer = None
            self._client_done.set()
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    def _dispatch(self, session: Session, incoming: Envelope) -> Envelope:
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
