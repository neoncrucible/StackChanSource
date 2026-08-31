from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .body_contract import CONTRACT
from .protocol import Envelope, MessageKind
from .transport import read_envelope, write_envelope


@dataclass(slots=True)
class SimulatedBody:
    device_id: str = "sim-body"
    presence: str = "booting"
    connected: bool = False
    last_motion: tuple[int, int, int] | None = None
    events: list[str] = field(default_factory=list)

    async def run_once(self, host: str, port: int) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = Envelope(
                MessageKind.HELLO,
                "device.hello",
                {
                    "device_id": self.device_id,
                    "capabilities": {
                        "display": [CONTRACT.display_width, CONTRACT.display_height],
                        "audio": [CONTRACT.audio_sample_rate_hz, CONTRACT.audio_channels],
                        "touch": ["press", "release", "swipe_forward", "swipe_backward"],
                        "motion": True,
                    },
                },
            )
            await write_envelope(writer, hello)
            ready = await read_envelope(reader)
            if ready.kind is not MessageKind.READY:
                raise RuntimeError(f"expected READY, got {ready.kind.value}")
            self.connected = True
            self.presence = str(ready.payload.get("presence", "idle"))

            heartbeat = Envelope(MessageKind.HEARTBEAT, "device.heartbeat")
            await write_envelope(writer, heartbeat)
            ack = await read_envelope(reader)
            if ack.kind is not MessageKind.ACK:
                raise RuntimeError(f"expected ACK, got {ack.kind.value}")
            self.events.append("heartbeat")
        finally:
            writer.close()
            await writer.wait_closed()
            self.connected = False

    def apply_motion_command(self, yaw: int, pitch: int, speed: int) -> tuple[int, int, int]:
        safe = CONTRACT.clamp_motion(yaw, pitch, speed)
        self.last_motion = safe
        return safe

    def touch_event(self, gesture: str) -> Envelope:
        allowed = {"press", "release", "swipe_forward", "swipe_backward"}
        if gesture not in allowed:
            raise ValueError(f"unsupported touch gesture: {gesture}")
        self.events.append(f"touch:{gesture}")
        return Envelope(MessageKind.EVENT, "body.touch", {"gesture": gesture})
