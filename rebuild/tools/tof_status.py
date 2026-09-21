"""Observe cached ToF4M distances (optionally Gesture); quit Kadence before use."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody
from kcore.sensors import read_tof_status, read_gesture_status


async def inspect(port, seconds, gesture):
    async with await RuntimeBody.open(RuntimeConfig("127.0.0.1", 8765, 5, 15), port=port) as runtime:
        deadline = asyncio.get_running_loop().time() + seconds
        previous = None
        while asyncio.get_running_loop().time() < deadline:
            s = await read_tof_status(runtime.host)
            distance = f"{s.distance_mm}mm" if s.fresh and s.valid else "unavailable"
            print(f"ToF4M: {s.state}; fresh={s.fresh}; valid={s.valid}; distance={distance}; "
                  f"seq={s.sequence}; age={s.age_ms}ms; raw_status={s.raw_status}; errors={s.errors}", flush=True)
            if gesture:
                g = await read_gesture_status(runtime.host)
                key = (g.state, g.fresh, g.event_sequence)
                if key != previous:
                    print(f"Gesture: {g.state}; fresh={g.fresh}; event_seq={g.event_sequence}; "
                          f"last={','.join(g.gestures) or 'none'}; event_age={g.event_age_ms}ms", flush=True)
                    previous = key
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--seconds", type=int, choices=range(1, 121), default=60)
    parser.add_argument("--gesture", action="store_true", help="Observe Gesture using the same serial connection")
    args = parser.parse_args()
    try:
        asyncio.run(inspect(args.port, args.seconds, args.gesture))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"TOF_STATUS unavailable: {type(exc).__name__}. Close serial owners and check firmware/port.")
        sys.exit(1)
