from __future__ import annotations

import asyncio

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.transport import read_envelope, write_envelope


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _heartbeat_survives_pending_command() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    command_seen = asyncio.Event()
    release_ack = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp15-body"})
            await write_envelope(writer, hello)
            host_ready = await read_envelope(reader)
            assert host_ready.kind is MessageKind.READY
            ready.set()

            command = await read_envelope(reader)
            assert command.kind is MessageKind.COMMAND
            assert command.name == "body.pose"
            command_seen.set()

            heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
            await write_envelope(writer, heartbeat)
            heartbeat_ack = await asyncio.wait_for(read_envelope(reader), timeout=0.25)
            assert heartbeat_ack.kind is MessageKind.ACK
            assert heartbeat_ack.name == "host.heartbeat"
            assert heartbeat_ack.request_id == heartbeat.request_id

            await asyncio.wait_for(release_ack.wait(), timeout=1.0)
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    command.name,
                    {"ok": True},
                    request_id=command.request_id,
                ),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    command_task = asyncio.create_task(host.send_body_pose(0, 400, timeout=1.0))
    await asyncio.wait_for(command_seen.wait(), timeout=1.0)
    await asyncio.sleep(0.05)
    assert not command_task.done(), "command completed before body ACK"

    release_ack.set()
    ack = await asyncio.wait_for(command_task, timeout=1.0)
    assert ack.kind is MessageKind.ACK
    assert ack.payload.get("ok") is True

    await body_task
    await host.close()


async def _cancel_keeps_session_healthy() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    command_seen = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp15-cancel"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            command = await read_envelope(reader)
            assert command.kind is MessageKind.COMMAND
            command_seen.set()

            heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
            await write_envelope(writer, heartbeat)
            heartbeat_ack = await asyncio.wait_for(read_envelope(reader), timeout=0.25)
            assert heartbeat_ack.kind is MessageKind.ACK
            assert heartbeat_ack.name == "host.heartbeat"
            assert heartbeat_ack.request_id == heartbeat.request_id

            await asyncio.sleep(0.05)
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    command.name,
                    {"ok": True},
                    request_id=command.request_id,
                ),
            )

            second_heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
            await write_envelope(writer, second_heartbeat)
            second_ack = await asyncio.wait_for(read_envelope(reader), timeout=0.25)
            assert second_ack.kind is MessageKind.ACK
            assert second_ack.name == "host.heartbeat"
            assert second_ack.request_id == second_heartbeat.request_id
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    command_task = asyncio.create_task(host.send_body_pose(20, 420, timeout=1.0))
    await asyncio.wait_for(command_seen.wait(), timeout=1.0)
    command_task.cancel()
    try:
        await command_task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled command unexpectedly completed")

    await body_task
    await host.close()


async def _main() -> None:
    await _heartbeat_survives_pending_command()
    await _cancel_keeps_session_healthy()


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT15_HOST_GATE PASS")
