from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import serial

from .config import RuntimeConfig
from .host import HostServer
from .serial_transport import SerialBodySession


@dataclass(slots=True)
class RuntimeBody:
    """Own the real serial body lifecycle for the host runtime."""

    host: HostServer
    session: SerialBodySession

    @classmethod
    async def open(
        cls,
        config: RuntimeConfig,
        *,
        port: str = "COM4",
        baud: int = 115200,
        ready_timeout: float = 30.0,
        serial_factory: Any = serial.Serial,
    ) -> "RuntimeBody":
        host = HostServer(config)
        ser = serial_factory(port, baud, timeout=0.25, write_timeout=3.0)
        try:
            ser.dtr = False
            ser.rts = False
            session = SerialBodySession(host, ser, port_name=port)
            await session.start(ready_timeout=ready_timeout)
            return cls(host=host, session=session)
        except Exception:
            try:
                ser.close()
            except Exception:
                pass
            raise

    async def close(self) -> None:
        await self.session.close()
        await self.host.close()

    async def send_body_pose(
        self,
        yaw: int,
        pitch: int,
        *,
        timeout: float = 8.0,
    ):
        return await self.host.send_body_pose(yaw, pitch, timeout=timeout)

    async def send_presentation_state(
        self,
        state: str,
        *,
        timeout: float = 3.0,
    ):
        return await self.host.send_presentation_state(state, timeout=timeout)

    async def send_voice_audio_check(
        self,
        *,
        timeout: float = 8.0,
    ):
        return await self.host.send_voice_audio_check(timeout=timeout)

    async def send_voice_turn(
        self,
        *,
        ssid: str,
        password: str,
        host: str,
        port: int,
        capture_ms: int = 4800,
        timeout: float = 90.0,
    ):
        return await self.host.send_voice_turn(
            ssid=ssid,
            password=password,
            host=host,
            port=port,
            capture_ms=capture_ms,
            timeout=timeout,
        )

    async def __aenter__(self) -> "RuntimeBody":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
