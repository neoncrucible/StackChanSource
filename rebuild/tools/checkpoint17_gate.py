from __future__ import annotations

import asyncio

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.transport import read_envelope, write_envelope


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _commands_are_single_flight() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    first_seen = asyncio.Event()
    allow_first_ack = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp17-single"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            first = await read_envelope(reader)
            assert first.kind is MessageKind.COMMAND
            assert first.name == "body.pose"
            first_seen.set()

            await asyncio.wait_for(allow_first_ack.wait(), timeout=1.0)
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, first.name, {"ok": True}, request_id=first.request_id),
            )

            second = await asyncio.wait_for(read_envelope(reader), timeout=0.5)
            assert second.kind is MessageKind.COMMAND
            assert second.name == "body.pose"
            assert second.request_id != first.request_id
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, second.name, {"ok": True}, request_id=second.request_id),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    first_task = asyncio.create_task(host.send_body_pose(0, 400, timeout=1.0))
    await asyncio.wait_for(first_seen.wait(), timeout=1.0)
    second_task = asyncio.create_task(host.send_body_pose(20, 420, timeout=1.0))

    await asyncio.sleep(0.05)
    assert len(host._pending) == 1, "more than one physical command became pending"
    assert not second_task.done(), "second command bypassed body ownership lock"

    allow_first_ack.set()
    first_ack = await asyncio.wait_for(first_task, timeout=1.0)
    second_ack = await asyncio.wait_for(second_task, timeout=1.0)
    assert first_ack.kind is MessageKind.ACK
    assert second_ack.kind is MessageKind.ACK

    await body_task
    await host.close()


async def _cancel_releases_command_lane() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    first_seen = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp17-cancel"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            first = await read_envelope(reader)
            first_seen.set()

            second = await asyncio.wait_for(read_envelope(reader), timeout=0.5)
            assert second.kind is MessageKind.COMMAND
            assert second.request_id != first.request_id

            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, first.name, {"ok": True}, request_id=first.request_id),
            )
            await write_envelope(
                writer,
                Envelope(MessageKind.ACK, second.name, {"ok": True}, request_id=second.request_id),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    first_task = asyncio.create_task(host.send_body_pose(30, 430, timeout=1.0))
    await asyncio.wait_for(first_seen.wait(), timeout=1.0)
    first_task.cancel()
    try:
        await first_task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled owner unexpectedly completed")

    second_ack = await asyncio.wait_for(host.send_body_pose(40, 440, timeout=1.0), timeout=1.0)
    assert second_ack.kind is MessageKind.ACK
    assert second_ack.payload.get("ok") is True

    await body_task
    await host.close()


async def _main() -> None:
    await _commands_are_single_flight()
    await _cancel_releases_command_lane()


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT17_HOST_GATE PASS")
