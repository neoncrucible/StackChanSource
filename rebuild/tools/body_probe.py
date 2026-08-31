from __future__ import annotations

import asyncio
from dataclasses import dataclass

from kcore.body_sim import SimulatedBody
from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.state import Presence


@dataclass(frozen=True, slots=True)
class BodyProbeResult:
    device_id: str
    host_presence: str
    events: tuple[str, ...]


def run_body_probe(config: RuntimeConfig) -> BodyProbeResult:
    async def scenario() -> BodyProbeResult:
        host = HostServer(config)
        address = await host.start(port=0)
        body = SimulatedBody()
        await body.run_once(*address)
        for _ in range(50):
            if host.state.presence is Presence.OFFLINE:
                break
            await asyncio.sleep(0.01)
        result = BodyProbeResult(
            device_id=body.device_id,
            host_presence=host.state.presence.value,
            events=tuple(body.events),
        )
        await host.close()
        return result

    return asyncio.run(scenario())
