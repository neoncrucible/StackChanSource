from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodyContract:
    display_width: int = 320
    display_height: int = 240
    audio_sample_rate_hz: int = 16_000
    audio_channels: int = 1
    safe_yaw_min_tenths: int = -320
    safe_yaw_max_tenths: int = 320
    safe_pitch_min_tenths: int = 30
    safe_pitch_max_tenths: int = 870
    min_motion_speed: int = 120
    max_motion_speed: int = 850
    default_motion_speed: int = 650
    position_tolerance_tenths: int = 40
    release_torque_after_motion: bool = True
    preserve_stored_zero_calibration: bool = True

    def clamp_motion(self, yaw: int, pitch: int, speed: int) -> tuple[int, int, int]:
        return (
            min(max(yaw, self.safe_yaw_min_tenths), self.safe_yaw_max_tenths),
            min(max(pitch, self.safe_pitch_min_tenths), self.safe_pitch_max_tenths),
            min(max(speed, self.min_motion_speed), self.max_motion_speed),
        )


CONTRACT = BodyContract()
