from pathlib import Path

import pytest

from kcore.config import load_runtime_config


def test_default_config_loads():
    path = Path(__file__).parents[1] / "config" / "default.toml"
    cfg = load_runtime_config(path)
    assert cfg.port == 8765
    assert cfg.device_timeout_seconds > cfg.heartbeat_seconds


def test_invalid_timeout_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('[runtime]\nheartbeat_seconds=10\ndevice_timeout_seconds=5\n', encoding="utf-8")
    with pytest.raises(ValueError, match="timeout"):
        load_runtime_config(path)
