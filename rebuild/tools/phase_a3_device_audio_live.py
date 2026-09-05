from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody

PORT = "COM4"


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _main() -> int:
    runtime: RuntimeBody | None = None
    try:
        runtime = await RuntimeBody.open(_config(), port=PORT, ready_timeout=30.0)

        print("PHASE_A3_DEVICE_AUDIO_LIVE READY speak during the device capture window")
        await asyncio.sleep(1.0)

        ack = await runtime.send_voice_audio_check(timeout=10.0)
        for key in ("ok", "capture", "playback", "handoff", "torque_released"):
            if ack.payload.get(key) is not True:
                raise RuntimeError(f"device audio proof missing: {key}")

        movement = await runtime.send_body_pose(0, 430, timeout=8.0)
        if movement.payload.get("executed") is not True:
            raise RuntimeError("post-audio body execution proof missing")
        if movement.payload.get("torque_released") is not True:
            raise RuntimeError("post-audio torque release proof missing")

        idle = await runtime.send_presentation_state("idle", timeout=3.0)
        if idle.payload.get("state") != "idle":
            raise RuntimeError("final idle acknowledgement missing")

        print(
            "PHASE_A3_DEVICE_AUDIO_LIVE PASS capture=1 playback=1 handoff=1 "
            "correlated=1 body_command=1 torque_released=1 recovery=1"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A3_DEVICE_AUDIO_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
