from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from kcore.config import load_runtime_config
from kcore.protocol import Envelope, MessageKind
from kcore.state import Presence, RuntimeState


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild host preflight")
    parser.add_argument("--config", default=str(ROOT / "config" / "default.toml"))
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("python", sys.version_info >= (3, 12), platform.python_version()))

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

    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<8} {detail}")

    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
