"""Single camera owner. Privacy is software access control, not sensor power control."""
from __future__ import annotations
import asyncio
import contextlib
from dataclasses import asdict, dataclass
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import time
import threading
import uuid


@dataclass(frozen=True)
class CameraConfig:
    policy: str = "OFF"
    privacy: bool = False
    source: str = "auto"
    address: str = "192.168.40.175"
    greetings: bool = False
    unknown_alerts: bool = False

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError("Unsupported camera settings.")
        result = cls(**value)
        if result.policy not in {"OFF", "EVENT_ONLY", "AWARE"} or result.source not in {"auto", "robot-camera", "unitv2-camera"}:
            raise ValueError("Choose a supported camera policy and source.")
        if any(type(getattr(result, field)) is not bool for field in ("privacy", "greetings", "unknown_alerts")):
            raise ValueError("Invalid camera switches.")
        try: address = ipaddress.IPv4Address(result.address)
        except (ValueError, TypeError): raise ValueError("Enter the UnitV2 IPv4 address.") from None
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise ValueError("Enter the UnitV2 LAN address.")
        return result

    @classmethod
    def load(cls, root):
        path = Path(root) / "camera-settings.json"
        if not path.exists(): return cls()
        try: return cls.parse(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError, OSError):
            # A damaged privacy preference must never silently re-enable acquisition.
            return cls(privacy=True)

    def save(self, root):
        path = Path(root) / "camera-settings.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)


@dataclass(frozen=True)
class CameraFrame:
    request_id: str
    frame_id: str
    source: str
    png: bytes
    width: int
    height: int
    captured_at: float
    elapsed_ms: int
    generation: int
    qr: tuple[str, ...] = ()


def decode_jpeg(jpeg):
    from PIL import Image
    with Image.open(io.BytesIO(jpeg)) as image:
        if image.format != "JPEG" or not (0 < image.width <= 1920 and 0 < image.height <= 1080):
            raise ValueError("Unsupported UnitV2 image dimensions.")
        image.load()
        image = image.convert("RGB")
        image.thumbnail((640, 480))
        output = io.BytesIO()
        image.save(output, format="PNG")
        png = output.getvalue()
        if len(png) > 700 * 1024: raise ValueError("Camera frame exceeds limit.")
        return png, image.width, image.height, ()


async def settled_thread(function, *args, on_cancel=None):
    """Cancellation revokes results immediately; retain ownership until worker settles."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try: return await asyncio.shield(task)
    except asyncio.CancelledError:
        if on_cancel: on_cancel()
        with contextlib.suppress(Exception): await task
        raise


class CameraManager:
    def __init__(self, robot_capture, *, emit=None, config=None, clock=time.monotonic):
        self.robot_capture = robot_capture
        self.emit = emit or (lambda *args: None)
        self.config = config or CameraConfig()
        self.clock = clock
        self.generation = 0
        self.state = "IDLE"
        self._active = None
        self._purpose = None
        self._fail_until = {}
        self._closed = False
        self._waiter = False

    def check(self, generation=None):
        if self._closed or self.config.privacy: raise RuntimeError("Camera access is blocked by privacy.")
        if generation is not None and generation != self.generation: raise RuntimeError("Camera request was superseded.")

    def publish(self, state=None):
        if state: self.state = state
        self.emit("camera_state", {"state": "PRIVACY" if self.config.privacy else self.state,
            "policy": self.config.policy, "privacy": self.config.privacy,
            "source": self.config.source, "producer_standby": "unsupported",
            "busy": self._active is not None})

    def configure(self, config):
        self.generation += 1
        self.config = config
        if self._active: self._active.cancel()
        self.publish("IDLE")

    async def close(self):
        self._closed = True
        self.generation += 1
        if self._active:
            self._active.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self._active
        self.publish("IDLE")

    async def acquire(self, *, purpose="manual", source=None, address=None, in_voice=None, timeout=25):
        self.check()
        if purpose == "automatic" and self.config.policy == "OFF": raise RuntimeError("Autonomous camera access is off.")
        source = source or self.config.source
        if source not in {"auto", "robot-camera", "unitv2-camera"}: raise ValueError("Choose a supported camera source.")
        # One explicit waiter, no unbounded queue; explicit work preempts automatic work.
        if self._active:
            if purpose == "automatic" or self._purpose != "automatic" or self._waiter:
                raise RuntimeError("Camera is busy. Try again shortly.")
            self._waiter = True
            try:
                self._active.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception): await self._active
            finally: self._waiter = False
        self.check()
        generation = self.generation
        self._purpose = purpose
        task = asyncio.create_task(self._capture(source, address or self.config.address, in_voice, timeout, generation))
        self._active = task
        try: return await task
        finally:
            if self._active is task:
                self._active = self._purpose = None
                if self.state != "FAULT": self.publish("IDLE")

    async def _capture(self, source, address, in_voice, timeout, generation):
        started = self.clock()
        deadline = started + timeout
        request_id = str(uuid.uuid4())
        sources = ("unitv2-camera", "robot-camera") if source == "auto" else (source,)
        self.publish("STARTING")
        for actual in sources:
            if self._fail_until.get(actual, 0) > self.clock(): continue
            self.check(generation)
            remaining = deadline - self.clock()
            if remaining <= 0: break
            try:
                self.publish("CAPTURING")
                if actual == "unitv2-camera":
                    interrupted = threading.Event()
                    def network():
                        from .unitv2_network import start_camera_stream, capture_jpeg
                        # Reserve time for AUTO fallback. Both operations share one deadline.
                        end = time.monotonic() + min(remaining, 12 if source == "auto" else remaining)
                        if interrupted.is_set(): raise RuntimeError("Camera request cancelled.")
                        start_camera_stream(address, timeout=min(5, max(.1, end-time.monotonic())))
                        if interrupted.is_set(): raise RuntimeError("Camera request cancelled.")
                        left = end-time.monotonic()
                        if left <= 0: raise TimeoutError()
                        return decode_jpeg(capture_jpeg(address, timeout=left))
                    png, width, height, qr = await settled_thread(network, on_cancel=interrupted.set)
                else:
                    async with asyncio.timeout(max(.1, deadline-self.clock())):
                        raw = await (in_voice() if in_voice else self.robot_capture())
                        from .vision import decode_image
                        png, qr = await settled_thread(decode_image, raw)
                        width, height = 320, 240
                self.check(generation)
                if self.clock() > deadline: raise TimeoutError()
                self._fail_until.pop(actual, None)
                return CameraFrame(request_id, str(uuid.uuid4()), actual, png, width, height,
                    time.time(), round((self.clock()-started)*1000), generation, tuple(qr))
            except asyncio.CancelledError: raise
            except Exception:
                self._fail_until[actual] = self.clock() + 15
        self.publish("FAULT")
        raise RuntimeError("Camera unavailable. Check its power, connection and address; retry after 15 seconds.")
