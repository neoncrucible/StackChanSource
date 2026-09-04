from __future__ import annotations

import json
import sys
import time
import uuid

import serial

PORT = "COM4"
BAUD = 115200
TIMEOUT_S = 8.0


def main() -> int:
    request_id = f"cp19-live-{uuid.uuid4().hex[:8]}"
    command = {
        "v": 1,
        "id": request_id,
        "ts": "host",
        "kind": "command",
        "name": "body.pose",
        "payload": {"yaw": 0, "pitch": 450},
    }

    with serial.Serial(PORT, BAUD, timeout=0.25, write_timeout=1.0) as ser:
        ser.dtr = False
        ser.rts = False
        time.sleep(0.25)
        ser.reset_input_buffer()

        raw = (json.dumps(command, separators=(",", ":")) + "\n").encode("utf-8")
        ser.write(raw)
        ser.flush()
        print(f"CP19_LIVE sent id={request_id} port={PORT}")

        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            line = ser.readline()
            if not line:
                continue
            try:
                text = line.decode("utf-8", errors="strict").strip()
            except UnicodeDecodeError:
                continue
            if not text.startswith("{"):
                continue
            try:
                incoming = json.loads(text)
            except json.JSONDecodeError:
                continue
            if incoming.get("id") != request_id:
                continue

            payload = incoming.get("payload")
            valid = (
                incoming.get("v") == 1
                and incoming.get("kind") == "ack"
                and incoming.get("name") == "body.pose"
                and isinstance(payload, dict)
                and payload.get("ok") is True
                and payload.get("executed") is True
                and payload.get("torque_released") is True
            )
            if not valid:
                print(f"CP19_LIVE FAIL unexpected correlated response: {incoming}")
                return 1

            print(
                "CP19_LIVE PASS correlated=1 executed=1 "
                "torque_released=1 transport=COM4"
            )
            return 0

    print("CP19_LIVE FAIL timeout waiting for correlated ACK")
    return 1


if __name__ == "__main__":
    sys.exit(main())
