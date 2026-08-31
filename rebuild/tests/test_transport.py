from __future__ import annotations

import asyncio

from kcore.protocol import Envelope, MessageKind
from kcore.transport import PeerClosed, read_envelope, write_envelope


def test_transport_round_trip() -> None:
    async def scenario() -> None:
        received: list[Envelope] = []

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received.append(await read_envelope(reader))
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        host, port, *_ = server.sockets[0].getsockname()
        _, writer = await asyncio.open_connection(host, port)
        sent = Envelope(MessageKind.EVENT, "test.event", {"value": 42})
        await write_envelope(writer, sent)
        writer.close()
        await writer.wait_closed()

        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.01)
        server.close()
        await server.wait_closed()

        assert received == [sent]

    asyncio.run(scenario())


def test_clean_close_raises_peer_closed() -> None:
    async def scenario() -> None:
        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        host, port, *_ = server.sockets[0].getsockname()
        reader, writer = await asyncio.open_connection(host, port)

        try:
            await read_envelope(reader)
            raise AssertionError("expected PeerClosed")
        except PeerClosed:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())
