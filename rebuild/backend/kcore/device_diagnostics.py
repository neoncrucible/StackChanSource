"""Small, typed camera/reset breadcrumbs from otherwise ignored serial logs.

Never forward raw firmware text: it can contain network credentials or payloads.
These observations have no protocol authority and cannot complete a command.
"""
from __future__ import annotations

import re

DEVICE_REASONS = frozenset({
    "sensor-detected", "driver-error", "dma-stop", "rebooting", "reset",
    "interrupt-watchdog", "task-watchdog", "load-prohibited",
    "store-prohibited", "illegal-instruction", "cache-error", "panic",
    "assertion", "stack-overflow", "backtrace",
})
DEVICE_COMPONENTS = frozenset({"gc0308", "dvp_cam", "dvp_gdma", "esp_cam_ctlr", "sccb-i2c"})
IMAGE_STAGES = frozenset({"image-header", "image-metadata", "image-data", "image-complete", "image-ack"})
IMAGE_REASONS = frozenset({"no-frame", "bad-header", "bad-format", "truncated", "interrupted", "unavailable"})
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LOG = re.compile(r"[IEW] \(\d+\) ([\w-]+): (.*)")


def parse_device_diagnostic(line: str) -> dict | None:
    if len(line) > 2048:
        return None
    line = _ANSI.sub("", line).strip()
    if line == "Rebooting...":
        return {"reason": "rebooting"}
    reset = re.match(r"rst:0x([0-9a-fA-F]{1,2}) \([A-Z0-9_]+\),boot:", line)
    if reset:
        return {"reason": "reset", "reset_code": int(reset[1], 16)}
    panic = re.fullmatch(r"Guru Meditation Error: Core\s+([01]) panic'ed \(([^\r\n]{1,100})\)\..*", line)
    if panic:
        reason = {
            "Interrupt wdt timeout on CPU0": "interrupt-watchdog",
            "Interrupt wdt timeout on CPU1": "interrupt-watchdog",
            "LoadProhibited": "load-prohibited", "StoreProhibited": "store-prohibited",
            "IllegalInstruction": "illegal-instruction",
            "Cache disabled but cached memory region accessed": "cache-error",
        }.get(panic[2], "panic")
        return {"reason": reason, "cpu": int(panic[1])}
    if line.startswith("assert failed: "):
        return {"reason": "assertion"}
    if re.fullmatch(r"\*\*\*ERROR\*\*\* A stack overflow in task .{1,64} has been detected\.", line):
        return {"reason": "stack-overflow"}
    if line.startswith("Backtrace:"):
        pairs = re.findall(r"0x([0-9a-fA-F]{8}):0x[0-9a-fA-F]{8}", line[10:])
        pcs = [int(pc, 16) for pc in pairs[:16] if 0x40000000 <= int(pc, 16) < 0x44000000]
        return {"reason": "backtrace", "backtrace": pcs} if pcs else None
    log = _LOG.fullmatch(line)
    if not log:
        return None
    component, message = log.groups()
    if component == "task_wdt" and message.startswith("Task watchdog got triggered"):
        return {"reason": "task-watchdog"}
    if message == "CAMERA state=quarantined reason=dma-stop":
        return {"reason": "dma-stop"}
    if component not in DEVICE_COMPONENTS:
        return None
    sensor = re.fullmatch(r"Detected Camera sensor PID=0x([0-9a-fA-F]{1,8})", message)
    if component == "gc0308" and sensor:
        return {"reason": "sensor-detected", "component": component, "sensor_pid": int(sensor[1], 16)}
    if line.startswith("E "):
        return {"reason": "driver-error", "component": component}
    return None
