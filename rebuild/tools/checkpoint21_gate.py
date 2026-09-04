from __future__ import annotations

import asyncio
from collections import deque

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.serial_transport import SerialBodySession
from kcore.state import Presence


class FakeSerial:
    def __init__(self, lines: list[bytes]):
        self.lines = deque(lines)
        self.writes: list[bytes] = []
        self.closed = False

    def readline(self) -> bytes:
        if self.closed:
            raise ConnectionError("fake serial closed")
        if self.lines:
            return self.lines.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def write(self, raw: bytes) -> int:
        if self.closed:
            raise ConnectionError("fake serial closed")
        self.writes.append(raw)
        text = raw.decode("utf-8").strip()
        command = Envelope.from_json(text)
        ack = Envelope(
            MessageKind.ACK,
            command.name,
            {"ok": True, "executed": True, "torque_released": True},
            request_id=command.request_id,
        )
        self.lines.append((ack.to_json() + "\n").encode("utf-8"))
        return len(raw)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _round_trip(host: HostServer, label: str) -> None:
    serial_port = FakeSerial([b"BODY_HEARTBEAT status=ok\n"])
    session = SerialBodySession(host, serial_port, port_name=label)
    await session.start(ready_timeout=1.0)
    assert host.state.presence is Presence.IDLE
    ack = await host.send_body_pose(0, 450, timeout=1.0)
    assert ack.payload.get("ok") is True
    assert ack.payload.get("executed") is True
    assert ack.payload.get("torque_released") is True
    await session.close()
    await asyncio.sleep(0)
    assert host._active_writer is None
    assert host._active_session is None
    assert not host._pending
    assert not host._retired
    assert host.state.presence is Presence.OFFLINE


async def _main() -> None:
    host = HostServer(_config())
    await _round_trip(host, "fake-a")
    await _round_trip(host, "fake-b")
    assert host.state.presence is Presence.OFFLINE


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT21_HOST_GATE PASS reconnect=1 stale_state=0 ownership_released=1")
