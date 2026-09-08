"""Reject startup stack regressions in the actual linked ESP32-S3 image.

These are individual compiler-generated frames, not a worst-case call-graph
proof. Hardware BOOT_STACK watermarks remain the measured qualification check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


FRAME_LIMITS = {
    "app_main": 512,
    "(anonymous namespace)::run_probe16()": 1024,
    "(anonymous namespace)::run_probe8()": 512,
    "(anonymous namespace)::probe8_draw_frame(bool)": 768,
}
MINIMUM_MAIN_STACK = 8192


def inspect_build(build: Path) -> dict:
    config = (build / "config" / "sdkconfig.h").read_text()
    match = re.search(r"^#define CONFIG_ESP_MAIN_TASK_STACK_SIZE (\d+)$", config, re.M)
    if not match:
        raise ValueError("Missing compiled main-task stack configuration")
    stack_bytes = int(match[1])
    cache = (build / "CMakeCache.txt").read_text()
    tool = re.search(r"^CMAKE_OBJDUMP:FILEPATH=(.+)$", cache, re.M)
    if not tool:
        raise ValueError("Missing matching Xtensa objdump in build configuration")
    elf = build / "kade-body-probe.elf"
    binary = build / "kade-body-probe.bin"
    assembly = subprocess.check_output([tool[1].strip(), "-d", "-C", str(elf)], text=True)
    frames = {}
    failures = []
    if stack_bytes < MINIMUM_MAIN_STACK:
        failures.append(f"main stack {stack_bytes} < {MINIMUM_MAIN_STACK}; update the active sdkconfig")
    for symbol, limit in FRAME_LIMITS.items():
        match = re.search(
            r"^[0-9a-f]+ <" + re.escape(symbol) + r">:\n[^\n]*\bentry\s+a1,\s*(0x[0-9a-f]+|\d+)",
            assembly, re.M,
        )
        if not match:
            failures.append(f"startup symbol/prologue unavailable: {symbol}")
            continue
        frame = int(match[1], 0)
        frames[symbol] = frame
        if frame > limit:
            failures.append(f"{symbol} frame {frame} > {limit}")
    if failures:
        raise ValueError("BOOT_STACK_GATE FAIL " + "; ".join(failures))
    return {
        "format": 1,
        "main_task_stack_bytes": stack_bytes,
        "compiled_frame_bytes": frames,
        "frame_limits_bytes": FRAME_LIMITS,
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "physical_boot_proven": False,
    }


def verify_and_record(build: Path) -> dict:
    report = inspect_build(build)
    (build / "boot_stack_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("BOOT_STACK_GATE PASS main_bytes=" + str(report["main_task_stack_bytes"])
          + " baseline_frame=" + str(report["compiled_frame_bytes"]["(anonymous namespace)::run_probe16()"])
          + " linked_image=1 hardware=unproven")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    verify_and_record(args.build)
