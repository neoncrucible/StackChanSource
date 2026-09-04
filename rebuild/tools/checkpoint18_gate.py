from __future__ import annotations

import asyncio
from pathlib import Path

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.transport import read_envelope, write_envelope


ROOT = Path(__file__).parents[1]
FIRMWARE = ROOT / "firmware" / "main" / "probe16.cpp"


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


def _require_firmware_contract() -> None:
    source = FIRMWARE.read_text(encoding="utf-8")
    for marker in (
        '"v":1',
        '"kind":"command"',
        '"name":"body.pose"',
        '"executed"',
        '"torque_released"',
        "p11_decode_pose(raw, &target)",
        "p9_release_torque()",
        "p10_verify_torque_released()",
        "return p16_make_ack(request_id, true, ack, ack_size);",
    ):
        if marker not in source:
            raise AssertionError(f"checkpoint18 missing firmware wire marker: {marker}")


async def _wire_lifecycle_round_trip() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    command_seen = asyncio.Event()
    physical_complete = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp18-body"})
            await write_envelope(writer, hello)
            host_ready = await read_envelope(reader)
            assert host_ready.kind is MessageKind.READY
            assert host_ready.name == "host.ready"
            assert host_ready.request_id == hello.request_id
            ready.set()

            command = await read_envelope(reader)
            assert command.version == 1
            assert command.kind is MessageKind.COMMAND
            assert command.name == "body.pose"
            assert isinstance(command.request_id, str) and command.request_id
            assert set(command.payload) == {"yaw", "pitch"}
            assert isinstance(command.payload["yaw"], int)
            assert isinstance(command.payload["pitch"], int)
            command_seen.set()

            # Model the CP16 ordering contract: no success ACK may leave the
            # body until physical completion (including torque release) exists.
            await asyncio.wait_for(physical_complete.wait(), timeout=1.0)
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    command.name,
                    {"ok": True, "executed": True, "torque_released": True},
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
    assert not command_task.done(), "host accepted body command before physical completion ACK"

    physical_complete.set()
    ack = await asyncio.wait_for(command_task, timeout=1.0)
    assert ack.version == 1
    assert ack.kind is MessageKind.ACK
    assert ack.name == "body.pose"
    assert ack.payload.get("ok") is True
    assert ack.payload.get("executed") is True
    assert ack.payload.get("torque_released") is True

    await body_task
    await host.close()


async def _correlation_cannot_cross_commands() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "cp18-correlation"})
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            first = await read_envelope(reader)
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    first.name,
                    {"ok": True, "executed": True, "torque_released": True},
                    request_id=first.request_id,
                ),
            )

            second = await read_envelope(reader)
            assert second.request_id != first.request_id
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    second.name,
                    {"ok": True, "executed": True, "torque_released": True},
                    request_id=second.request_id,
                ),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    first_ack = await host.send_body_pose(-20, 380, timeout=1.0)
    second_ack = await host.send_body_pose(20, 420, timeout=1.0)
    assert first_ack.request_id != second_ack.request_id

    await body_task
    await host.close()


async def _main() -> None:
    _require_firmware_contract()
    await _wire_lifecycle_round_trip()
    await _correlation_cannot_cross_commands()


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT18_HOST_GATE PASS")
