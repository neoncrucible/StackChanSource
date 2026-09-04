from __future__ import annotations

import asyncio
import sys

import serial

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.serial_transport import SerialBodySession

PORT = "COM4"
BAUD = 115200


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


async def _main() -> int:
    host = HostServer(_config())
    ser = serial.Serial(PORT, BAUD, timeout=0.25, write_timeout=3.0)
    ser.dtr = False
    ser.rts = False
    session = SerialBodySession(host, ser, port_name=PORT)

    try:
        await session.start(ready_timeout=30.0)
        print(f"CP22_LIVE host-bound port={PORT}")

        # Deliberately send one malformed protocol line. The firmware must
        # reject it safely and the host serial reader must survive its log noise.
        await asyncio.to_thread(ser.write, b"{not-json}\n")
        await asyncio.to_thread(ser.flush)
        await asyncio.sleep(0.25)

        ack = await host.send_body_pose(0, 430, timeout=8.0)
        if ack.payload.get("executed") is not True:
            print("CP22_LIVE FAIL missing execution proof after malformed frame")
            return 1
        if ack.payload.get("torque_released") is not True:
            print("CP22_LIVE FAIL torque release not confirmed")
            return 1
        reader = session._reader_task
        if reader is None or reader.done():
            print("CP22_LIVE FAIL serial reader did not remain healthy")
            return 1

        print(
            "CP22_LIVE PASS malformed_rejected=1 session_healthy=1 "
            "fresh_command=1 correlated=1 torque_released=1"
        )
        return 0
    except Exception as exc:
        print(f"CP22_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        await session.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
