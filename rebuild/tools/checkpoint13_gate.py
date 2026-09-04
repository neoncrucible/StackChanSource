from __future__ import annotations

import asyncio

from kcore.body_contract import CONTRACT
from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.transport import read_envelope, write_envelope


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _correlated_round_trip() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()
    observed: dict[str, object] = {}

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(
                MessageKind.HELLO,
                "device.hello",
                {"device_id": "cp13-body"},
            )
            await write_envelope(writer, hello)
            host_ready = await read_envelope(reader)
            assert host_ready.kind is MessageKind.READY
            assert host_ready.request_id == hello.request_id
            ready.set()

            command = await read_envelope(reader)
            assert command.kind is MessageKind.COMMAND
            assert command.name == "body.pose"
            observed["request_id"] = command.request_id
            observed["yaw"] = command.payload["yaw"]
            observed["pitch"] = command.payload["pitch"]

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
    ack = await host.send_body_pose(9999, -9999, timeout=1.0)
    assert ack.kind is MessageKind.ACK
    assert ack.request_id == observed["request_id"]
    assert observed["yaw"] == CONTRACT.safe_yaw_max_tenths
    assert observed["pitch"] == CONTRACT.safe_pitch_min_tenths
    await body_task
    await host.close()


async def _timeout_then_recover() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(
                MessageKind.HELLO,
                "device.hello",
                {"device_id": "cp13-timeout-body"},
            )
            await write_envelope(writer, hello)
            host_ready = await read_envelope(reader)
            assert host_ready.kind is MessageKind.READY
            ready.set()

            first = await read_envelope(reader)
            assert first.kind is MessageKind.COMMAND

            second = await read_envelope(reader)
            assert second.kind is MessageKind.COMMAND
            assert second.request_id != first.request_id
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    second.name,
                    {"ok": True},
                    request_id=second.request_id,
                ),
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
        raise AssertionError("missing ACK did not time out")

    ack = await host.send_body_pose(10, 410, timeout=1.0)
    assert ack.kind is MessageKind.ACK
    assert ack.payload.get("ok") is True

    await body_task
    await host.close()


async def _reject_bad_ack() -> None:
    host = HostServer(_config())
    address = await host.start(port=0)
    ready = asyncio.Event()

    async def body() -> None:
        reader, writer = await asyncio.open_connection(*address)
        try:
            hello = Envelope(
                MessageKind.HELLO,
                "device.hello",
                {"device_id": "cp13-bad-ack-body"},
            )
            await write_envelope(writer, hello)
            await read_envelope(reader)
            ready.set()

            command = await read_envelope(reader)
            await write_envelope(
                writer,
                Envelope(
                    MessageKind.ACK,
                    "body.wrong",
                    {"ok": True},
                    request_id=command.request_id,
                ),
            )
        finally:
            writer.close()
            await writer.wait_closed()

    body_task = asyncio.create_task(body())
    await asyncio.wait_for(ready.wait(), timeout=1.0)

    try:
        await host.send_body_pose(0, 400, timeout=1.0)
    except RuntimeError as exc:
        assert "ACK name mismatch" in str(exc)
    else:
        raise AssertionError("mismatched ACK was accepted")

    await body_task
    await host.close()


async def _main() -> None:
    await _correlated_round_trip()
    await _timeout_then_recover()
    await _reject_bad_ack()


if __name__ == "__main__":
    asyncio.run(_main())
    print("CHECKPOINT13_HOST_GATE PASS")
