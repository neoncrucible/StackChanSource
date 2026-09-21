"""Read the cached UnitV2 UART transport status; never captures or moves anything."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from kcore.config import RuntimeConfig
from kcore.device_control import request_device
from kcore.runtime import RuntimeBody


async def inspect(port: str) -> None:
    config = RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)
    async with await RuntimeBody.open(config, port=port) as runtime:
        reply = await request_device(runtime.host, "camera.unitv2.status", timeout=3.0)
        p = reply.payload
        print(
            "UnitV2: "
            f"uart_ready={p.get('uart_ready')} "
            f"command_sent={p.get('command_sent')} "
            f"response_seen={p.get('response_seen')} "
            f"valid_json={p.get('valid_json')} "
            f"parse_errors={p.get('parse_errors')} "
            f"bytes_rx={p.get('bytes_rx')} "
            f"last_response_age_ms={p.get('last_response_age_ms')}"
        )
        if p.get("running") is not None:
            print(f"  running={p['running']}")
        if p.get("msg") is not None:
            print(f"  msg={p['msg']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Close Kadence/serial monitors before running this diagnostic."
    )
    parser.add_argument("--port", default="COM4")
    args = parser.parse_args()
    try:
        asyncio.run(inspect(args.port))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"UNITV2_STATUS unavailable: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
