#!/usr/bin/env python3
"""Materialise the Kade Eye binary assets from a split base64 archive."""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRMWARE_ROOT = ROOT.parent
ARCHIVE_SHA256 = "b74d819ae5732a786822486c3e61be859769c68b067d5820245c51688a334b2b"

FILES = {
    "kade_idle1.png": (
        "3be5526019daea57af61f1b09b9761fb95726e994def6327d84bfe9945f3397f",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_idle1.png",
    ),
    "kade_idle2.png": (
        "0d5348cd0684af27ba8faa25481ba2a1265a82842b5af96906aac30529f20413",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_idle2.png",
    ),
    "kade_blink.png": (
        "072b643fd9eab522ea8f3dc7e4a7ff645523d6194cfe8d940138534ca5577445",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_blink.png",
    ),
    "kade_blink2.png": (
        "cd295d7c53dee7eb242cf165e78eec095a3078ac64510068281160703c957d33",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_blink2.png",
    ),
    "kade_listening.png": (
        "fd10b36f4e26aa8746051490bc20c8ab916154078e0b7586175c2cdcd78830bd",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_listening.png",
    ),
    "kade_error.png": (
        "b85d2f29af5f97f713e43e654c7f825569b7a1cf39fdcbbc9f0583f360aa3da3",
        FIRMWARE_ROOT / "main" / "assets" / "assets_bin" / "kade_error.png",
    ),
    "kade_boot.ogg": (
        "de5c69b96b3fbf5639ede61e34deb9cf00b74b0955a936700ccd3c0d25716b3e",
        FIRMWARE_ROOT / "main" / "assets" / "sfx" / "kade_boot.ogg",
    ),
}


def load_archive() -> bytes:
    parts = sorted(ROOT.glob("kade_assets.zip.b64.part*"))
    if not parts:
        raise FileNotFoundError("No Kade Eye archive parts were found")

    encoded = "".join(part.read_text(encoding="ascii") for part in parts)
    archive = base64.b64decode(encoded, validate=True)
    actual_sha256 = hashlib.sha256(archive).hexdigest()
    if actual_sha256 != ARCHIVE_SHA256:
        raise ValueError(
            f"Archive checksum mismatch: expected {ARCHIVE_SHA256}, got {actual_sha256}"
        )
    return archive


def write_verified(payload: bytes, expected_sha256: str, destination: Path) -> None:
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Checksum mismatch for {destination.name}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_sha256:
        print(f"Kade asset unchanged: {destination}")
        return

    destination.write_bytes(payload)
    print(f"Kade asset prepared: {destination}")


def main() -> None:
    archive = load_archive()
    with zipfile.ZipFile(io.BytesIO(archive), "r") as bundle:
        available = set(bundle.namelist())
        missing = set(FILES) - available
        if missing:
            raise ValueError(f"Kade Eye archive is missing: {sorted(missing)}")

        for name, (checksum, destination) in FILES.items():
            write_verified(bundle.read(name), checksum, destination)


if __name__ == "__main__":
    main()
