from __future__ import annotations

import asyncio

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.transport import read_envelope, write_envelope


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _late_timeout_ack_is_quarantined() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp14-timeout"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            first = await read_envelope(reader)
            await asyncio.sleep(0.10)
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, first.name, {"ok": True}, request_id=first.request_id),
            )

            second = await read_envelope(reader)
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, second.name, {"ok": True}, request_id=second.request_id),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    try:
        await host.send_body_pose(0, 400, timeout=0.05)
    except TimeoutError:
        pass
    else:
        raise AssertionError("first command did not time out")

    await asyncio.sleep(0.10)
    ack = await host.send_body_pose(10, 410, timeout=1.0)
    assert ack.kind is MessageKind.ACK
    assert ack.payload.get("ok") is True

    await body_task
    await host.close()


async def _late_cancel_ack_is_quarantined() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    first_seen = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp14-cancel"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            first = await read_envelope(reader)
            first_seen.set()
            await asyncio.sleep(0.05)
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, first.name, {"ok": True}, request_id=first.request_id),
            )

            second = await read_envelope(reader)
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, second.name, {"ok": True}, request_id=second.request_id),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    command_task = asyncio.create_task(host.send_body_pose(20, 420, timeout=1.0))
    await asyncio.wait_for(first_seen.wait(), timeout=1.0)
    command_task.cancel()
    try:
        await command_task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled command unexpectedly completed")

    await asyncio.sleep(0.10)
    ack = await host.send_body_pose(30, 430, timeout=1.0)
    assert ack.kind is MessageKind.ACK
    assert ack.payload.get("ok") is True

    await body_task
    await host.close()


async def _unsolicited_ack_still_fails_closed() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)

    reader, writer = await asyncio.open_connection(*address)
    hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp14-unsolicited"})
    await write_envelope(writer, hello)
    await read_envelope(reader)

    unsolicited = Envelope(MessageKind.ACK, "body.pose", {"ok": True}, request_id="never-issued")
    await write_envelope(writer, unsolicited)
    error = await read_envelope(reader)
    assert error.kind is MessageKind.ERROR
    assert error.name == "host.error"
    assert "unexpected correlated response" in str(error.payload.get("message", ""))

    writer.close()
    await writer.wait_closed()
    await host.close()


async def _main() -> None:
    await _late_timeout_ack_is_quarantined()
    await _late_cancel_ack_is_quarantined()
    await _unsolicited_ack_still_fails_closed()


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT14_HOST_GATE PASS")
