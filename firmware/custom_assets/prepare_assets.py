#!/usr/bin/env python3
"""Materialise Kade Eye binary assets from repository-safe base64 sources."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRMWARE_ROOT = ROOT.parent

ASSETS = {
    "kade_idle1.png": "3be5526019daea57af61f1b09b9761fb95726e994def6327d84bfe9945f3397f",
    "kade_idle2.png": "0d5348cd0684af27ba8faa25481ba2a1265a82842b5af96906aac30529f20413",
    "kade_blink.png": "072b643fd9eab522ea8f3dc7e4a7ff645523d6194cfe8d940138534ca5577445",
    "kade_blink2.png": "cd295d7c53dee7eb242cf165e78eec095a3078ac64510068281160703c957d33",
    "kade_listening.png": "fd10b36f4e26aa8746051490bc20c8ab916154078e0b7586175c2cdcd78830bd",
    "kade_error.png": "b85d2f29af5f97f713e43e654c7f825569b7a1cf39fdcbbc9f0583f360aa3da3",
}

AUDIO = {
    "kade_boot.ogg": "de5c69b96b3fbf5639ede61e34deb9cf00b74b0955a936700ccd3c0d25716b3e",
}


def materialise(name: str, expected_sha256: str, destination: Path) -> None:
    source = ROOT / f"{name}.b64"
    if not source.is_file():
        raise FileNotFoundError(f"Missing encoded asset: {source}")

    payload = base64.b64decode(source.read_text(encoding="ascii"))
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Checksum mismatch for {name}: expected {expected_sha256}, got {actual_sha256}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_sha256:
        print(f"Kade asset unchanged: {destination}")
        return

    destination.write_bytes(payload)
    print(f"Kade asset prepared: {destination}")


def main() -> None:
    image_dir = FIRMWARE_ROOT / "main" / "assets" / "assets_bin"
    audio_dir = FIRMWARE_ROOT / "main" / "assets" / "sfx"

    for name, checksum in ASSETS.items():
        materialise(name, checksum, image_dir / name)

    for name, checksum in AUDIO.items():
        materialise(name, checksum, audio_dir / name)


if __name__ == "__main__":
    main()
