"""Check UnitV2 Wi-Fi frame decoding; no files saved and no COM port opened."""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from kcore.unitv2_network import capture_jpeg, start_camera_stream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--count", type=int, choices=range(1, 11), default=3)
    args = parser.parse_args()
    from PIL import Image
    try:
        print("UNITV2_START selecting Camera Stream", flush=True)
        start_camera_stream(args.address)
        for number in range(1, args.count + 1):
            start = time.monotonic()
            jpeg = capture_jpeg(args.address, timeout=15.0 if number == 1 else 5.0)
            with Image.open(io.BytesIO(jpeg)) as frame:
                width, height = frame.size
                if frame.format != "JPEG" or not (0 < width <= 1920 and 0 < height <= 1080):
                    raise ValueError("unexpected camera format or dimensions")
                frame.load()
            elapsed = time.monotonic() - start
            print(f"UNITV2_FRAME PASS sample={number} width={width} height={height} "
                  f"bytes={len(jpeg)} seconds={elapsed:.3f} "
                  f"sha256={hashlib.sha256(jpeg).hexdigest()[:16]}", flush=True)
            if number < args.count:
                time.sleep(1)
    except Exception as exc:
        print(f"UNITV2_FRAME FAIL {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
