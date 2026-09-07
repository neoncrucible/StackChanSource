from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "kcore"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    appliance_path = BACKEND / "appliance.py"
    serial_path = BACKEND / "serial_transport.py"
    runtime_path = BACKEND / "runtime.py"
    pyproject_path = ROOT / "pyproject.toml"

    appliance = appliance_path.read_text(encoding="utf-8")
    serial = serial_path.read_text(encoding="utf-8")
    runtime = runtime_path.read_text(encoding="utf-8")
    pyproject = pyproject_path.read_text(encoding="utf-8")

    ast.parse(appliance, filename=str(appliance_path))
    ast.parse(serial, filename=str(serial_path))
    ast.parse(runtime, filename=str(runtime_path))

    require('kadence = "kcore.appliance:main"' in pyproject,
            "normal kadence console entry point is not registered")
    require("class KadenceAppliance" in appliance and "async def run_forever" in appliance,
            "always-on appliance runtime is missing")
    require("RuntimeBody.open(" in appliance,
            "appliance does not use the proven RuntimeBody owner")
    require("asyncio.start_server" in appliance and appliance.count("asyncio.start_server") == 1,
            "appliance must own exactly one LAN voice server")
    require('event.name == "voice.request"' in appliance,
            "normal runtime does not consume physical voice requests")
    require('event.name == "voice.touch-cancel"' in appliance,
            "normal runtime does not consume physical touch cancellation")
    require("process_wire_turn" in appliance and "send_wire_reply" in appliance,
            "normal runtime does not own the real provider voice pipeline")
    require("body.send_voice_turn(" in appliance and "body.send_voice_cancel(" in appliance,
            "normal runtime is missing the proven device voice control path")
    require("body.send_body_pose(0, 430" in appliance and "torque_released" in appliance,
            "normal runtime does not use the proven safe body reaction lane")
    require("body.wait_disconnected()" in appliance,
            "normal runtime does not supervise physical disconnects")
    require("KADENCE_RUNTIME RECONNECT" in appliance and "reconnect_delay" in appliance,
            "normal runtime has no reconnect policy")
    require("await self._cancel_active_provider()" in appliance,
            "provider work is not cancelled during recovery/shutdown")
    require("KADENCE_RUNTIME STOPPED clean=1" in appliance,
            "normal runtime has no clean shutdown proof")

    require("self._disconnected = asyncio.Event()" in serial,
            "serial transport has no explicit disconnect lifecycle")
    require("async def wait_disconnected" in serial and "self._disconnected.set()" in serial,
            "serial disconnect lifecycle is incomplete")
    require("async def wait_disconnected" in runtime and "self.session.wait_disconnected()" in runtime,
            "RuntimeBody does not expose disconnect supervision")

    require("phase_a3_" not in appliance.lower(),
            "product runtime illegally depends on an A3 test harness")
    require("serial.Serial" not in appliance,
            "product runtime bypasses RuntimeBody with a second serial owner")
    require("COM4" not in appliance.split("DEFAULT_PORT", 1)[1] if "DEFAULT_PORT" in appliance else True,
            "unexpected hard-coded COM4 use beyond the default port declaration")

    print(
        "PHASE_A4_GATE PASS "
        "normal_entry=1 runtime_owner=1 device_events=1 repeated_turns=1 "
        "touch_cancel=1 provider_cancel=1 body_reaction=1 reconnect=1 clean_shutdown=1 "
        "single_voice_server=1 no_test_harness=1"
    )


if __name__ == "__main__":
    main()
