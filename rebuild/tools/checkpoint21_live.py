from __future__ import annotations

import asyncio
import sys

import serial

from kcore.config import RuntimeConfig
from kcore.host import HostServer
from kcore.serial_transport import SerialBodySession
from kcore.state import Presence

PORT = "COM4"
BAUD = 115200


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


def _open_serial() -> serial.Serial:
    ser = serial.Serial(PORT, BAUD, timeout=0.25, write_timeout=3.0)
    ser.dtr = False
    ser.rts = False
    return ser


async def _bind_and_command(host: HostServer, label: str) -> None:
    session = SerialBodySession(host, _open_serial(), port_name=PORT)
    try:
        await session.start(ready_timeout=30.0)
        print(f"CP21_LIVE {label}-bound port={PORT}")
        ack = await host.send_body_pose(0, 450, timeout=8.0)
        payload = ack.payload
        if payload.get("executed") is not True or payload.get("torque_released") is not True:
            raise RuntimeError(f"{label} missing physical completion proof")
    finally:
        await session.close()


async def _main() -> int:
    host = HostServer(_config())
    try:
        await _bind_and_command(host, "first")
        await asyncio.sleep(0.25)
        if host.state.presence is not Presence.OFFLINE:
            raise RuntimeError("host did not return offline after first disconnect")
        if host._active_writer is not None or host._active_session is not None or host._pending:
            raise RuntimeError("host retained stale serial ownership after disconnect")

        await _bind_and_command(host, "reconnect")
        await asyncio.sleep(0.25)
        if host.state.presence is not Presence.OFFLINE:
            raise RuntimeError("host did not return offline after reconnect close")

        print(
            "CP21_LIVE PASS reconnect=1 second_command=1 stale_state=0 "
            "ownership_released=1 torque_released=1"
        )
        return 0
    except Exception as exc:
        print(f"CP21_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
