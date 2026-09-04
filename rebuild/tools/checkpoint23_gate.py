from __future__ import annotations

import asyncio
import json
from queue import Queue, Empty

from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


class FakeSerial:
    def __init__(self, port, baud, *, timeout, write_timeout):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.dtr = True
        self.rts = True
        self.closed = False
        self._rx: Queue[bytes] = Queue()
        self._rx.put(b"I (100) BODY_HEARTBEAT status=ok\n")

    def readline(self) -> bytes:
        if self.closed:
            return b""
        try:
            return self._rx.get(timeout=self.timeout)
        except Empty:
            return b""

    def reset_input_buffer(self) -> None:
        return None

    def write(self, raw: bytes) -> int:
        command = json.loads(raw.decode("utf-8").strip())
        ack = {
            "v": 1,
            "id": command["id"],
            "ts": "device",
            "kind": "ack",
            "name": command["name"],
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


async def _main() -> None:
    runtime = await RuntimeBody.open(
        _config(),
        port="FAKE23",
        ready_timeout=1.0,
        serial_factory=FakeSerial,
    )
    try:
        assert runtime.session.port_name == "FAKE23"
        assert runtime.host._active_session is not None
        assert runtime.host._active_session.hello_seen is True

        first = await runtime.send_body_pose(-15, 420, timeout=1.0)
        second = await runtime.send_body_pose(15, 440, timeout=1.0)
        for ack in (first, second):
            assert ack.payload.get("ok") is True
            assert ack.payload.get("executed") is True
            assert ack.payload.get("torque_released") is True
        assert first.request_id != second.request_id
    finally:
        await runtime.close()

    assert runtime.host._active_writer is None
    assert runtime.host._active_session is None


if __name__ == "__main__":
    asyncio.run(_main())
    print(
        "CHECKPOINT23_HOST_GATE PASS runtime_owner=1 sequential_commands=1 "
        "correlated=1 clean_shutdown=1"
    )
