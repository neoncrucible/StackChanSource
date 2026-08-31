from __future__ import annotations

import asyncio

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.state import Presence
from kcore.transport import read_envelope, write_envelope


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


def test_handshake_heartbeat_and_disconnect() -> None:
    async def scenario() -> None:
        host = HostServer(_config())
        address = await host.start(port=0)
        reader, writer = await asyncio.open_connection(*address)

        hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "test-device"})
        await write_envelope(writer, hello)
        ready = await read_envelope(reader)
        assert ready.kind is MessageKind.READY
        assert ready.request_id == hello.request_id
        assert host.state.presence is Presence.IDLE

        heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
        await write_envelope(writer, heartbeat)
        ack = await read_envelope(reader)
        assert ack.kind is MessageKind.ACK
        assert ack.request_id == heartbeat.request_id

        writer.close()
        await writer.wait_closed()
        for _ in range(50):
            if host.state.presence is Presence.OFFLINE:
                break
            await asyncio.sleep(0.01)
        assert host.state.presence is Presence.OFFLINE
        await host.close()

    asyncio.run(scenario())


def test_second_client_is_rejected() -> None:
    async def scenario() -> None:
        host = HostServer(_config())
        address = await host.start(port=0)
        first_reader, first_writer = await asyncio.open_connection(*address)
        hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": "first"})
        await write_envelope(first_writer, hello)
        await read_envelope(first_reader)

        second_reader, second_writer = await asyncio.open_connection(*address)
        busy = await read_envelope(second_reader)
        assert busy.kind is MessageKind.ERROR
        assert busy.name == "host.busy"

        second_writer.close()
        await second_writer.wait_closed()
        first_writer.close()
        await first_writer.wait_closed()
        await host.close()

    asyncio.run(scenario())
