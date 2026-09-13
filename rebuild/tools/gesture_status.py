"""Observe cached PAJ7620 events; close the desktop server before use."""
import argparse
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody
from kcore.sensors import read_gesture_status

async def inspect(port, seconds):
    async with await RuntimeBody.open(RuntimeConfig("127.0.0.1", 8765, 5, 15), port=port) as runtime:
        deadline = asyncio.get_running_loop().time() + seconds
        previous = None
        while asyncio.get_running_loop().time() < deadline:
            s = await read_gesture_status(runtime.host)
            key = (s.state, s.fresh, s.event_sequence)
            if key != previous:
                print(f"Gesture: {s.state}; fresh={s.fresh}; event_seq={s.event_sequence}; "
                      f"last={','.join(s.gestures) or 'none'}; event_age={s.event_age_ms}ms", flush=True)
                previous = key
            await asyncio.sleep(0.25)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--seconds", type=int, choices=range(1, 121), default=30)
    args = parser.parse_args()
    try:
        asyncio.run(inspect(args.port, args.seconds))
    except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"GESTURE_STATUS unavailable: {type(exc).__name__}. Close serial owners and check firmware/port.")
        sys.exit(1)
