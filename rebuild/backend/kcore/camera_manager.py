"""Single camera owner. Privacy is software access control, not sensor power control."""
from __future__ import annotations
import asyncio
import contextlib
from dataclasses import asdict, dataclass, replace
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
    perception_enabled: bool = False

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError("Unsupported camera settings.")
        result = cls(**value)
        if result.policy not in {"OFF", "EVENT_ONLY", "AWARE"} or result.source not in {"auto", "robot-camera", "unitv2-camera"}:
            raise ValueError("Choose a supported camera policy and source.")
        if any(type(getattr(result, field)) is not bool for field in ("privacy", "greetings", "unknown_alerts", "perception_enabled")):
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

    @classmethod
    def companion_defaults(cls, root):
        """Apply the requested autonomous defaults once; retain privacy and rollback.

        A later choice of OFF is never undone on restart. Per-person recognition
        and greeting preferences and an explicit camera choice stay intact.
        """
        root = Path(root)
        marker = root/'companion-defaults.json'
        config = cls.load(root)
        if marker.exists(): return config
        previous = root/'camera-settings.json'
        backup = root/'camera-settings.pre-0.6.1.json'
        if previous.exists() and not backup.exists(): backup.write_bytes(previous.read_bytes())
        config = replace(config, policy='AWARE', perception_enabled=True, greetings=True)
        config.save(root)
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'format':1,'version':'0.6.1'}))
        temporary.replace(marker)
        return config


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
    try:
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
    except (ValueError, OSError, Image.DecompressionBombError):
        from .camera_faults import CameraFault
        raise CameraFault('invalid_image') from None


async def settled_thread(function, *args, on_cancel=None):
    """Cancellation revokes results immediately; retain ownership until worker settles."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try: return await asyncio.shield(task)
    except asyncio.CancelledError:
        if on_cancel: on_cancel()
        # Several consumers may cancel the same request (privacy, explicit work,
        # shutdown). Repeated cancellation must not abandon a live OS worker.
        while not task.done():
            try: await asyncio.shield(task)
            except asyncio.CancelledError: continue
            except Exception: break
        with contextlib.suppress(asyncio.CancelledError, Exception): task.result()
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
        self.failure = None
        self._closed = False
        self._waiter = False
        from .unitv2_lifecycle import UnitV2Owner
        self.unitv2 = UnitV2Owner(self.emit)

    def check(self, generation=None):
        if self._closed or self.config.privacy: raise RuntimeError("Camera access is blocked by privacy.")
        if generation is not None and generation != self.generation: raise RuntimeError("Camera request was superseded.")

    def publish(self, state=None):
        if state: self.state = state
        self.emit("camera_state", {"state": "PRIVACY" if self.config.privacy else self.state,
            "policy": self.config.policy, "privacy": self.config.privacy,
            "source": self.config.source, "producer_standby": self.unitv2.status.get("state", "UNKNOWN"),
            "busy": self._active is not None, "error_code": self.failure.code if self.failure else None})
        self.unitv2.publish()

    def configure(self, config):
        self.generation += 1
        self._fail_until.clear()
        self.failure = None
        self.config = config
        if self._active: self._active.cancel()
        self.unitv2.revoke()
        self.publish("IDLE")

    def report_failure(self, error, *, source='unitv2-camera'):
        from .camera_faults import camera_fault
        fault = camera_fault(error)
        if self.failure is None or self.failure.code != fault.code:
            self.emit('camera_issue', {'code':fault.code, 'source':source})
        self.failure = fault
        self.publish('FAULT')
        return fault

    async def prepare_automatically(self, *, pause=asyncio.sleep):
        """A late camera boot must recover without repeating SSH setup."""
        generation, attempt = self.generation, 0
        config = self.config
        if config.privacy or config.source == 'robot-camera' or not config.perception_enabled or config.policy == 'OFF': return
        while not self._closed and generation == self.generation and not self.config.privacy:
            if self._active or self.unitv2.lock.locked() or self.unitv2._holds:
                await pause(1)
                continue
            try:
                async with asyncio.timeout(20):
                    await self.unitv2.ensure_ready(config.address, guard=lambda:self.check(generation))
            except asyncio.CancelledError: raise
            except Exception as exc:
                if self._closed or generation != self.generation or self.config.privacy: return
                self.report_failure(exc)
                await pause((2, 5, 10, 30)[min(attempt, 3)])
                attempt += 1
            else:
                self.failure = None
                self.publish('IDLE')
                return

    async def settle_settings(self):
        if self._active:
            with contextlib.suppress(asyncio.CancelledError, Exception): await self._active
        # Reconcile the configured device even if this host has not captured yet.
        await self.unitv2.stop(self.config.address)

    async def unitv2_control(self, mode):
        if mode == "KEEP_READY": self.check()
        self.generation += 1
        self.unitv2.revoke()
        if self._active:
            self._active.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self._active
        await self.unitv2.control_mode(mode, self.config.address)
        self.publish("IDLE")

    async def close(self):
        if self._closed: return
        self._closed = True
        self.generation += 1
        if self._active:
            self._active.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self._active
        with contextlib.suppress(Exception): await self.unitv2.close()
        self.publish("IDLE")

    async def acquire(self, *, purpose="manual", source=None, address=None, in_voice=None, timeout=25):
        self.check()
        if purpose == "automatic" and self.config.policy == "OFF": raise RuntimeError("Autonomous camera access is off.")
        if purpose == "automatic" and self.unitv2.mode == "STOPPED": raise RuntimeError("Autonomous camera access is paused.")
        source = source or self.config.source
        if source not in {"auto", "robot-camera", "unitv2-camera"}: raise ValueError("Choose a supported camera source.")
        if purpose == "automatic":
            if not self.config.perception_enabled: raise RuntimeError("Automatic perception is not enabled.")
            if source != "robot-camera" and not self.unitv2.verified:
                raise RuntimeError("Run the UnitV2 start / stop check before enabling automatic capture.")
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
        task = asyncio.create_task(self._capture(source, address or self.config.address, in_voice, timeout, generation, allow_legacy=purpose=="manual", automatic=purpose=="automatic"))
        self._active = task
        try: return await task
        finally:
            if self._active is task:
                self._active = self._purpose = None
                if self.state != "FAULT": self.publish("IDLE")

    async def _capture(self, source, address, in_voice, timeout, generation, *, allow_legacy=True, automatic=False):
        started = self.clock()
        deadline = started + timeout
        request_id = str(uuid.uuid4())
        sources = ("unitv2-camera", "robot-camera") if source == "auto" else (source,)
        self.publish("STARTING")
        error = self.failure
        actual = sources[0]
        for actual in sources:
            failure_key = (actual, address)
            if automatic and self._fail_until.get(failure_key, 0) > self.clock(): continue
            self.check(generation)
            remaining = deadline - self.clock()
            if remaining <= 0: break
            try:
                self.publish("CAPTURING")
                if actual == "unitv2-camera":
                    managed = await self.unitv2.capture(address, timeout=min(remaining,12))
                    if managed is not None:
                        png, width, height, qr = managed
                    else:
                        if not allow_legacy:
                            from .camera_faults import CameraFault
                            raise CameraFault('pairing_missing')
                        png, width, height, qr = await self._legacy_unitv2(address, remaining, source)
                else:
                    async with asyncio.timeout(max(.1, deadline-self.clock())):
                        raw = await (in_voice() if in_voice else self.robot_capture())
                        from .vision import decode_image
                        png, qr = await settled_thread(decode_image, raw)
                        width, height = 320, 240
                self.check(generation)
                if self.clock() > deadline: raise TimeoutError()
                self._fail_until.pop(failure_key, None)
                self.failure = None
                return CameraFrame(request_id, str(uuid.uuid4()), actual, png, width, height,
                    time.time(), round((self.clock()-started)*1000), generation, tuple(qr))
            except asyncio.CancelledError: raise
            except Exception as exc:
                error = exc
                self._fail_until[failure_key] = self.clock() + 15
        raise self.report_failure(error or TimeoutError(), source=actual) from None

    async def _legacy_unitv2(self, address, remaining, source):
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
        return await settled_thread(network, on_cancel=interrupted.set)
