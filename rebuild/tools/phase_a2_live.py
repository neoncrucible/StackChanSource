from __future__ import annotations

import asyncio
import threading
import time

import serial

from kcore.config import RuntimeConfig
from kcore.runtime import RuntimeBody

PORT = "COM4"


def _config() -> RuntimeConfig:
    return RuntimeConfig("127.0.0.1", 8765, 5.0, 15.0)


class CaptureSerial:
    """Thin pyserial proxy that retains diagnostic lines for live A2 assertions."""

    def __init__(self, port, baud, *, timeout, write_timeout):
        self._serial = serial.Serial(
            port,
            baud,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        self._lines: list[str] = []
        self._lock = threading.Lock()

    @property
    def dtr(self):
        return self._serial.dtr

    @dtr.setter
    def dtr(self, value):
        self._serial.dtr = value

    @property
    def rts(self):
        return self._serial.rts

    @rts.setter
    def rts(self, value):
        self._serial.rts = value

    def readline(self) -> bytes:
        raw = self._serial.readline()
        if raw:
            try:
                text = raw.decode("utf-8", errors="strict").strip()
            except UnicodeDecodeError:
                text = ""
            if text:
                with self._lock:
                    self._lines.append(text)
        return raw

    def reset_input_buffer(self) -> None:
        self._serial.reset_input_buffer()

    def write(self, raw: bytes) -> int:
        return self._serial.write(raw)

    def flush(self) -> None:
        self._serial.flush()

    def close(self) -> None:
        self._serial.close()

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._lines)


async def _wait_for_line(
    ser: CaptureSerial,
    needle: str,
    *,
    after: int = 0,
    timeout: float,
) -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lines = ser.snapshot()
        for index in range(after, len(lines)):
            if needle in lines[index]:
                return index, lines[index]
        await asyncio.sleep(0.05)
    raise TimeoutError(f"live marker not observed: {needle}")


async def _main() -> int:
    holder: dict[str, CaptureSerial] = {}

    def factory(port, baud, *, timeout, write_timeout):
        wrapper = CaptureSerial(
            port,
            baud,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        holder["serial"] = wrapper
        return wrapper

    runtime: RuntimeBody | None = None
    try:
        runtime = await RuntimeBody.open(
            _config(),
            port=PORT,
            ready_timeout=30.0,
            serial_factory=factory,
        )
        ser = holder["serial"]
        start = len(ser.snapshot())

        pre_index, _ = await _wait_for_line(
            ser,
            "reason=presence-local",
            after=start,
            timeout=22.0,
        )

        ack = await runtime.send_body_pose(0, 430, timeout=8.0)
        if ack.payload.get("executed") is not True:
            raise RuntimeError("body execution proof missing")
        if ack.payload.get("torque_released") is not True:
            raise RuntimeError("torque release proof missing")

        complete_index, _ = await _wait_for_line(
            ser,
            "reason=body-complete",
            after=pre_index,
            timeout=3.0,
        )

        between = ser.snapshot()[pre_index:complete_index]
        if any("reason=presence-complete" in line for line in between):
            raise RuntimeError("local lifecycle completed before command takeover")

        await _wait_for_line(
            ser,
            "reason=presence-local",
            after=complete_index + 1,
            timeout=22.0,
        )

        print(
            "PHASE_A2_LIVE PASS precondition=1 interrupt=1 command=1 "
            "correlated=1 torque_released=1 recovery=1"
        )
        return 0
    except Exception as exc:
        print(f"PHASE_A2_LIVE FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if runtime is not None:
            await runtime.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
