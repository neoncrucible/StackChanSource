from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from body_probe import run_body_probe
from kcore.config import RuntimeConfig


def test_simulated_body_completes_host_handshake():
    cfg = RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)
    result = run_body_probe(cfg)
    assert result.device_id == "sim-body"
    assert result.host_presence == "offline"
    assert result.events == ("heartbeat",)
