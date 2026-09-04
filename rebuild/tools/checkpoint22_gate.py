from __future__ import annotations

import asyncio
import json
from collections import deque

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.serial_transport import SerialBodySession


class FakeSerial:
    def __init__(self) -> None:
        self.lines: deque[bytes] = deque([
            b"I (123) boot: diagnostic noise\n",
            b"BODY_HEARTBEAT status=ok\n",
        ])
        self.writes: list[bytes] = []
        self.closed = False

    def readline(self) -> bytes:
        if self.lines:
            return self.lines.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def write(self, raw: bytes) -> int:
        self.writes.append(raw)
        return len(raw)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _main() -> None:
    host = HostServer(_config())
    serial = FakeSerial()
    session = SerialBodySession(host, serial, port_name="FAKE")
    await session.start(ready_timeout=1.0)

    task = asyncio.create_task(host.send_body_pose(0, 420, timeout=1.0))
    while not serial.writes:
        await asyncio.sleep(0)

    outgoing = json.loads(serial.writes[-1].decode("utf-8"))
    request_id = outgoing["id"]

    # Noise, malformed JSON, an unrelated envelope and a late retired-looking
    # response must not wedge the serial reader or resolve the live command.
    serial.lines.extend([
        b"I (456) app: unrelated log line\n",
        b"{not-json}\n",
        json.dumps({
            "v": 1,
            "id": "unrelated-id",
            "ts": "device",
            "kind": "event",
            "name": "device.note",
            "payload": {"x": 1},
        }, separators=(",", ":")).encode() + b"\n",
        json.dumps({
            "v": 1,
            "id": request_id,
            "ts": "device",
            "kind": "ack",
            "name": "body.pose",
            "payload": {"ok": True, "executed": True, "torque_released": True},
        }, separators=(",", ":")).encode() + b"\n",
    ])

    ack = await task
    assert ack.request_id == request_id
    assert ack.payload.get("executed") is True
    assert ack.payload.get("torque_released") is True
    assert session._reader_task is not None and not session._reader_task.done()

    await session.close()
    print("CHECKPOINT22_HOST_GATE PASS noise_tolerant=1 malformed_ignored=1 session_healthy=1")


if __name__ == "__main__":
    asyncio.run(_main())
