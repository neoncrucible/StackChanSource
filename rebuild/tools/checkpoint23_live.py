from __future__ import annotations

import asyncio
import sys

from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody

PORT = "COM4"


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _main() -> int:
    runtime: RuntimeBody | None = None
    try:
        runtime = await RuntimeBody.open(_config(), port=PORT, ready_timeout=30.0)
        print(f"CP23_LIVE runtime-bound port={PORT}")

        first = await runtime.send_body_pose(-12, 420, timeout=8.0)
        second = await runtime.send_body_pose(12, 440, timeout=8.0)

        for ack in (first, second):
            if ack.payload.get("executed") is not True:
                print("CP23_LIVE FAIL missing execution proof")
                return 1
            if ack.payload.get("torque_released") is not True:
                print("CP23_LIVE FAIL torque release not confirmed")
                return 1

        if first.request_id == second.request_id:
            print("CP23_LIVE FAIL request correlation reused")
            return 1

        print(
            "CP23_LIVE PASS runtime_owner=1 sequential_commands=1 "
            "correlated=1 torque_released=1 clean_path=1"
        )
        return 0
    except Exception as exc:
        print(f"CP23_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
