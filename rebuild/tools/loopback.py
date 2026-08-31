from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from kcore.config import RuntimeConfig, load_runtime_config
from kcore.host import HostServer
from kcore.protocol import Envelope, MessageKind
from kcore.state import Presence
from kcore.transport import read_envelope, write_envelope


@dataclass(frozen=True, slots=True)
class ProbeResult:
    address: str
    device_id: str
    sequence: int


async def probe(config: RuntimeConfig) -> ProbeResult:
    host = HostServer(config)
    bind_host, bind_port = await host.start(port=0)
    reader, writer = await asyncio.open_connection(bind_host, bind_port)
    device_id = "loopback-core"

    try:
        hello = Envelope(MessageKind.HELLO, "device.hello", {"device_id": device_id})
        await write_envelope(writer, hello)
        ready = await read_envelope(reader)
        if ready.kind is not MessageKind.READY or ready.request_id != hello.request_id:
            raise RuntimeError("HELLO/READY correlation failed")
        if ready.payload.get("presence") != Presence.IDLE.value:
            raise RuntimeError("host did not enter idle state")

        heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
        await write_envelope(writer, heartbeat)
        ack = await read_envelope(reader)
        if ack.kind is not MessageKind.ACK or ack.request_id != heartbeat.request_id:
            raise RuntimeError("heartbeat ACK correlation failed")

        return ProbeResult(
            address=f"{bind_host}:{bind_port}",
            device_id=device_id,
            sequence=int(ready.payload["sequence"]),
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass
        await host.close()


def run_probe(config: RuntimeConfig) -> ProbeResult:
    return asyncio.run(probe(config))


def main() -> int:
    config = load_runtime_config(ROOT / "config" / "default.toml")
    result = run_probe(config)
    print(f"PASS  loopback {result.address} device={result.device_id} seq={result.sequence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
