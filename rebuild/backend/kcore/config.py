from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    host: str
    port: int
    heartbeat_seconds: float
    device_timeout_seconds: float


def load_runtime_config(path: str | Path) -> RuntimeConfig:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    runtime = raw.get("runtime", {})
    cfg = RuntimeConfig(
        host=str(runtime.get("host", "127.0.0.1")),
        port=int(runtime.get("port", 8765)),
        heartbeat_seconds=float(runtime.get("heartbeat_seconds", 5.0)),
        device_timeout_seconds=float(runtime.get("device_timeout_seconds", 15.0)),
    )
    if not 1 <= cfg.port <= 65535:
        raise ValueError("runtime.port must be between 1 and 65535")
    if cfg.heartbeat_seconds <= 0 or cfg.device_timeout_seconds <= 0:
        raise ValueError("runtime timing values must be positive")
    if cfg.device_timeout_seconds <= cfg.heartbeat_seconds:
        raise ValueError("device timeout must exceed heartbeat interval")
    return cfg
