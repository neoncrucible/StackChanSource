from __future__ import annotations

import json
from pathlib import Path

from kcore.commands import PoseCommand, decode_body_command
from kcore.protocol import Envelope, MessageKind


def main() -> None:
    request = Envelope(
        MessageKind.COMMAND,
        "body.pose",
        {"yaw": 0, "pitch": 400},
        request_id="cp12-correlation",
    )
    assert decode_body_command(request) == PoseCommand(yaw=0, pitch=400)

    encoded = request.to_json()
    decoded = Envelope.from_json(encoded)
    assert decoded.request_id == request.request_id
    assert decoded.kind is MessageKind.COMMAND
    assert decoded.name == "body.pose"

    ack = Envelope(
        MessageKind.ACK,
        "body.pose",
        {"ok": True},
        request_id=decoded.request_id,
    )
    ack_roundtrip = Envelope.from_json(ack.to_json())
    assert ack_roundtrip.kind is MessageKind.ACK
    assert ack_roundtrip.request_id == request.request_id
    assert ack_roundtrip.payload == {"ok": True}

    raw = json.loads(ack_roundtrip.to_json())
    assert raw["v"] == 1
    assert raw["id"] == "cp12-correlation"

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "rebuild/firmware/main/probe12.cpp").read_text(encoding="utf-8")

    required = (
        "p12_extract_request_id",
        "p12_make_ack",
        "p12_decode_ack",
        "p12_protocol_round_trip",
        "correlated=1",
        "ack_roundtrip=1",
        "reject_malformed=1",
        "torque=released",
    )
    for token in required:
        assert token in source, f"checkpoint marker missing: {token}"

    forbidden = (
        "nvs_set_",
        "setCurrentAngleAsZero",
        "resetZeroCalibration",
        "NVS_READWRITE",
    )
    for token in forbidden:
        assert token not in source, f"forbidden calibration mutation token: {token}"

    print("CHECKPOINT12_HOST_GATE PASS")


if __name__ == "__main__":
    main()
