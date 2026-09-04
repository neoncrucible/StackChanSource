from __future__ import annotations

import asyncio
import json
import queue

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.serial_transport import SerialBodySession


class FakeSerial:
    def __init__(self) -> None:
        self._rx: queue.Queue[bytes] = queue.Queue()
        self._rx.put(b"I (100) probe: PROBE19 status=ready transport=usb-serial-jtag\n")
        self.closed = False

    def readline(self) -> bytes:
        if self.closed:
            return b""
        try:
            return self._rx.get(timeout=0.05)
        except queue.Empty:
            return b""

    def reset_input_buffer(self) -> None:
        while True:
            try:
                self._rx.get_nowait()
            except queue.Empty:
                return

    def write(self, raw: bytes) -> int:
        command = json.loads(raw.decode("utf-8").strip())
        assert command["v"] == 1
        assert command["kind"] == "command"
        assert command["name"] == "body.pose"
        self._rx.put(b"I (200) probe: BODY_HEARTBEAT status=ok heap=328000\n")
        ack = {
            "v": 1,
            "id": command["id"],
            "ts": "device",
            "kind": "ack",
            "name": "body.pose",
            "payload": {
                "ok": True,
                "executed": True,
                "torque_released": True,
            },
        }
        self._rx.put((json.dumps(ack, separators=(",", ":")) + "\n").encode("utf-8"))
        return len(raw)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _main() -> None:
    host = HostServer(_config())
    fake = FakeSerial()
    session = SerialBodySession(host, fake, port_name="FAKE")
    await session.start(ready_timeout=1.0)
    assert host._active_session is not None
    assert host._active_session.hello_seen is True

    ack = await host.send_body_pose(0, 450, timeout=1.0)
    assert ack.payload.get("ok") is True
    assert ack.payload.get("executed") is True
    assert ack.payload.get("torque_released") is True

    await session.close()
    assert host._active_writer is None
    assert host._active_session is None


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT20_HOST_GATE PASS")
