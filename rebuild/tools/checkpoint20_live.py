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
        print(f"CP20_LIVE host-bound port={PORT}")
        ack = await host.send_body_pose(0, 450, timeout=8.0)
        payload = ack.payload
        if payload.get("executed") is not True:
            print("CP20_LIVE FAIL missing execution proof")
            return 1
        if payload.get("torque_released") is not True:
            print("CP20_LIVE FAIL torque release not confirmed")
            return 1
        print(
            "CP20_LIVE PASS host_server=1 serial_bound=1 correlated=1 "
            "executed=1 torque_released=1"
        )
        return 0
    except Exception as exc:
        print(f"CP20_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        await session.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
