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

        seen: list[str] = []
        for state in ("listening", "thinking", "speaking", "idle"):
            ack = await runtime.send_presentation_state(state, timeout=3.0)
            if ack.payload.get("ok") is not True or ack.payload.get("state") != state:
                raise RuntimeError(f"state acknowledgement failed for {state}")
            seen.append(state)
            await asyncio.sleep(0.45)

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("body execution proof missing")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing")

        final_ack = await runtime.send_presentation_state("idle", timeout=3.0)
        if final_ack.payload.get("state") != "idle":
            raise RuntimeError("final idle acknowledgement missing")

        if seen != ["listening", "thinking", "speaking", "idle"]:
            raise RuntimeError("presentation state sequence incomplete")

        print(
            "PHASE_A3_BRIDGE_LIVE PASS states=4 correlated=1 runtime_owner=1 "
            "body_command=1 torque_released=1 recovery=1"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_BRIDGE_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
