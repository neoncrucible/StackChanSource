#!/usr/bin/env python3
"""Validate the vendored Kade Eye assets and generate an embedded C++ header."""

from __future__ import annotations

import argparse
import io
import struct
import wave
from pathlib import Path

PNG_ASSETS = {
    "idle1_png": Path("optic-eye/idle1.png"),
    "idle2_png": Path("optic-eye/idle2.png"),
    "blink_png": Path("optic-eye/blink.png"),
    "blink2_png": Path("optic-eye/blink2.png"),
    "listening_png": Path("optic-eye/listening.png"),
    "listening2_png": Path("optic-eye/listening2.png"),
    "error_png": Path("optic-eye/error.png"),
}
WAV_ASSETS = {
    "boot_wav": Path("audio/boot.wav"),
    "chirp_wav": Path("audio/chirp.wav"),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# The original listening cue contains a long reverberant/fading tail. That made
# the audible end ambiguous: a user could naturally begin speaking while the
# tail was still ringing, before the post-cue capture gate opened. Preserve the
# recognisable start of the source cue, but render a deterministic dry version
# with a short fade to true digital silence.
DRY_CHIRP_ACTIVE_MS = 500
DRY_CHIRP_FADE_MS = 25
DRY_CHIRP_SILENCE_MS = 70


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a valid PNG with an IHDR chunk")
    return struct.unpack(">II", data[16:24])


def validate_wav(path: Path) -> str:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        compression = wav.getcomptype()
    if compression != "NONE":
        raise ValueError(f"{path}: compressed WAV is not supported ({compression})")
    if channels not in (1, 2):
        raise ValueError(f"{path}: expected mono or stereo, got {channels} channels")
    if sample_width not in (1, 2, 3, 4):
        raise ValueError(f"{path}: unsupported sample width {sample_width * 8} bits")
    if sample_rate <= 0 or frames <= 0:
        raise ValueError(f"{path}: invalid sample rate or empty audio")
    return f"{channels}ch {sample_width * 8}-bit {sample_rate}Hz, {frames} frames"


def pcm_sample_to_s16(data: bytes, offset: int, sample_width: int) -> int:
    if sample_width == 1:
        return (data[offset] - 128) << 8
    value = int.from_bytes(
        data[offset : offset + sample_width],
        byteorder="little",
        signed=True,
    )
    if sample_width == 2:
        return value
    if sample_width == 3:
        return value >> 8
    if sample_width == 4:
        return value >> 16
    raise ValueError(f"unsupported sample width {sample_width}")


def build_dry_chirp(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        total_frames = source.getnframes()
        pcm = source.readframes(total_frames)

    active_frames = min(
        total_frames,
        max(1, sample_rate * DRY_CHIRP_ACTIVE_MS // 1000),
    )
    fade_frames = min(
        active_frames,
        max(1, sample_rate * DRY_CHIRP_FADE_MS // 1000),
    )
    silence_frames = max(1, sample_rate * DRY_CHIRP_SILENCE_MS // 1000)
    frame_width = channels * sample_width

    dry_samples: list[int] = []
    for frame_index in range(active_frames):
        frame_offset = frame_index * frame_width
        mixed = 0
        for channel in range(channels):
            sample_offset = frame_offset + channel * sample_width
            mixed += pcm_sample_to_s16(pcm, sample_offset, sample_width)
        mixed //= channels

        fade_start = active_frames - fade_frames
        if frame_index >= fade_start:
            remaining = active_frames - 1 - frame_index
            mixed = mixed * remaining // fade_frames

        dry_samples.append(max(-32768, min(32767, mixed)))

    dry_samples.extend([0] * silence_frames)

    output = io.BytesIO()
    with wave.open(output, "wb") as rendered:
        rendered.setnchannels(1)
        rendered.setsampwidth(2)
        rendered.setframerate(sample_rate)
        rendered.writeframes(struct.pack(f"<{len(dry_samples)}h", *dry_samples))
    return output.getvalue()


def emit_array(name: str, data: bytes) -> str:
    lines = [f"alignas(4) inline constexpr std::uint8_t {name}[] = {{"]
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        lines.append("    " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines.append("};")
    lines.append(f"inline constexpr std::size_t {name}_size = sizeof({name});")
    return "\n".join(lines)


def generate(input_root: Path, output: Path) -> None:
    arrays: list[tuple[str, bytes]] = []

    for name, relative_path in PNG_ASSETS.items():
        path = input_root / relative_path
        data = path.read_bytes()
        width, height = png_dimensions(data)
        if (width, height) != (320, 240):
            raise ValueError(f"{path}: expected 320x240, got {width}x{height}")
        print(f"validated {relative_path}: {width}x{height}, {len(data)} bytes")
        arrays.append((name, data))

    for name, relative_path in WAV_ASSETS.items():
        wav_path = input_root / relative_path
        wav_description = validate_wav(wav_path)
        if name == "chirp_wav":
            wav_data = build_dry_chirp(wav_path)
            with wave.open(io.BytesIO(wav_data), "rb") as rendered:
                rendered_ms = round(
                    rendered.getnframes() * 1000 / rendered.getframerate()
                )
            print(
                f"validated {relative_path}: {wav_description}; "
                f"rendered dry cue {rendered_ms}ms "
                f"({DRY_CHIRP_ACTIVE_MS}ms active + "
                f"{DRY_CHIRP_SILENCE_MS}ms silence), {len(wav_data)} bytes"
            )
        else:
            wav_data = wav_path.read_bytes()
            print(
                f"validated {relative_path}: {wav_description}, "
                f"{len(wav_data)} bytes"
            )
        arrays.append((name, wav_data))

    output.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        "// Generated by tools/generate_kade_assets.py. Do not edit.",
        "#pragma once",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace kade_assets {",
    ]
    for name, data in arrays:
        parts.extend(("", emit_array(name, data)))
    parts.extend(("", "}  // namespace kade_assets", ""))
    output.write_text("\n".join(parts), encoding="utf-8")
    print(f"generated {output} ({output.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.input_root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
