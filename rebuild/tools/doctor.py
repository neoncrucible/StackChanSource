from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

from body_probe import run_body_probe
from kcore.config import load_runtime_config
from kcore.protocol import Envelope, MessageKind
from kcore.state import Presence, RuntimeState
from loopback import run_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild host preflight")
    parser.add_argument("--config", default=str(ROOT / "config" / "default.toml"))
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("python", sys.version_info >= (3, 12), platform.python_version()))

    cfg = None
    try:
        cfg = load_runtime_config(args.config)
        checks.append(("config", True, f"{cfg.host}:{cfg.port}"))
    except Exception as exc:
        checks.append(("config", False, str(exc)))

    try:
        state = RuntimeState()
        state.transition(Presence.IDLE)
        state.transition(Presence.LISTENING)
        env = Envelope(MessageKind.HELLO, "doctor", {"state": state.presence.value})
        Envelope.from_json(env.to_json())
        checks.append(("core", True, f"protocol-v{env.version}"))
    except Exception as exc:
        checks.append(("core", False, str(exc)))

    if cfg is not None:
        try:
            probe = run_probe(cfg)
            checks.append(("loopback", True, f"{probe.address} seq={probe.sequence}"))
        except Exception as exc:
            checks.append(("loopback", False, str(exc)))

        try:
            body = run_body_probe(cfg)
            ok = body.host_presence == "offline" and "heartbeat" in body.events
            checks.append(("body-sim", ok, f"{body.device_id} -> {body.host_presence}"))
        except Exception as exc:
            checks.append(("body-sim", False, str(exc)))

    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<8} {detail}")

    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
