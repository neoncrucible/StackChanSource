"""Read cached hub discovery using the existing serial owner; never moves the body."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody
from kcore.sensors import read_sensor_status


async def inspect(port, watch):
    config = RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)
    async with await RuntimeBody.open(config, port=port) as runtime:
        for sample in range(watch):
            status = await read_sensor_status(runtime.host)
            print(f"Hub 0x{status.hub_address:02X}: {status.hub}; seq={status.sequence}; "
                  f"age={status.age_ms}ms; fresh={status.fresh}; errors={status.hub_errors}")
            if status.hub_address == 0x70:
                print("ENV III QMP6988 also uses 0x70: resolve the hub address before connecting it.")
            if status.upstream_addresses:
                print("Upstream (excluded from channels):", ", ".join(f"0x{a:02X}" for a in status.upstream_addresses))
            for channel, health in enumerate(status.channels):
                addresses = ", ".join(f"0x{a:02X}" for a in health.addresses) or "none"
                print(f"  Channel {channel}: {health.state}; responding={addresses}; errors={health.errors}")
            if sample + 1 < watch:
                await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Close Signal Console/serial monitors before running this diagnostic.")
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--watch", type=int, choices=range(1, 13), default=3, metavar="1..12")
    args = parser.parse_args()
    try:
        asyncio.run(inspect(args.port, args.watch))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"SENSOR_STATUS unavailable: {type(exc).__name__}. Check the port, close other serial owners, and use Phase 1 firmware.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
