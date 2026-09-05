from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "backend" / "kcore" / "host.py"
RUNTIME = ROOT / "backend" / "kcore" / "runtime.py"
BRIDGE = ROOT / "backend" / "kcore" / "runtime_bridge.py"
PROBE19 = ROOT / "firmware" / "main" / "probe19.cpp"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> None:
    host = HOST.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    bridge = BRIDGE.read_text(encoding="utf-8")
    probe19 = PROBE19.read_text(encoding="utf-8")

    require(host, "async def send_presentation_state", "host presentation command")
    require(host, '"presentation.state"', "versioned presentation command name")
    require(host, '"tool-working"', "presentation state contract")
    require(host, "self._pending[command.request_id] = pending", "correlated pending lifecycle")
    require(host, "self._retire_request(command.request_id)", "timeout retirement")
    require(host, "response.payload.get(\"state\") != state", "state acknowledgement validation")

    require(runtime, "async def send_presentation_state", "RuntimeBody presentation method")
    require(runtime, "self.host.send_presentation_state", "RuntimeBody host delegation")

    require(bridge, "class RuntimePresentationBridge", "interaction bridge")
    require(bridge, "await self.body.send_presentation_state", "bridge RuntimeBody ownership")

    require(probe19, '"presentation.state"', "firmware presentation protocol command")
    require(probe19, "p19_execute_presentation_command", "firmware presentation decoder")
    require(probe19, "p19_make_presentation_ack", "firmware correlated state ACK")
    require(probe19, "presence_interaction_begin();", "presence yield on active host state")
    require(probe19, "presence_interaction_end();", "presence resume on idle host state")

    # The proven physical movement authority must still be the CP16 path.
    require(probe19, "p16_execute_pose_command(line, ack, sizeof(ack))", "proven body executor")
    require(probe19, "p9_release_torque();", "body reject torque release")
    require(probe19, "PROBE19 status=ack-sent executed=1 torque=released", "body completion telemetry")

    print(
        "PHASE_A3_BRIDGE_GATE PASS protocol=v1 correlated=1 runtime_owner=1 "
        "presence_yield=1 body_path=preserved"
    )


if __name__ == "__main__":
    main()
