"""Deliberate, bounded camera snapshots. Frames and QR text are data only."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import io
import json
import re
import struct
import time
import uuid
from pathlib import Path

from .storage import KadencePaths

IMAGE_BYTES = 320*240*2


async def read_media_auth(reader, *, magic: bytes, token: str):
    hello = await reader.readexactly(36)
    if hello[:4] != magic or not hmac.compare_digest(hello[4:], token.encode("ascii")):
        raise ValueError("invalid media authentication")


async def read_image(reader, *, emit=None) -> bytes:
    stage, received, expected = "image-header", 0, 4
    reason = None

    def report():
        if emit:
            data = {"stage": stage, "received_bytes": received, "expected_bytes": expected}
            if reason: data["reason"] = reason
            with contextlib.suppress(Exception):
                emit("camera_transfer", data)

    try:
        report()
        magic = await reader.readexactly(4)
        received = 4
        if magic == b"KDI0":
            reason = "no-frame"
            raise RuntimeError("Camera did not produce an image. Try again with the robot idle.")
        if magic != b"KDI1":
            reason = "bad-header"
            raise ValueError("invalid image header")
        stage, received, expected = "image-metadata", 0, 8
        report()
        width, height, size = struct.unpack("!HHI", await reader.readexactly(8))
        received = 8
        if (width, height, size) != (320, 240, IMAGE_BYTES):
            reason = "bad-format"
            raise ValueError("image exceeds fixed QVGA contract")
        stage, received, expected = "image-data", 0, IMAGE_BYTES
        report()
        raw = bytearray()
        while received < expected:
            chunk = await reader.read(min(16384, expected - received))
            if not chunk:
                raise asyncio.IncompleteReadError(bytes(raw), expected)
            raw.extend(chunk)
            received += len(chunk)
        stage = "image-complete"
        report()
        return bytes(raw)
    except BaseException as exc:
        if isinstance(exc, asyncio.IncompleteReadError):
            received = len(exc.partial)
            reason = "truncated"
        reason = reason or ("interrupted" if isinstance(exc, asyncio.CancelledError) else "unavailable")
        report()
        raise


def decode_image(raw: bytes) -> tuple[bytes, list[str]]:
    if len(raw) != IMAGE_BYTES: raise ValueError("invalid RGB565 frame size")
    from PIL import Image
    rgb = bytearray(320*240*3)
    for i in range(0, len(raw), 2):
        pixel = (raw[i]<<8)|raw[i+1]
        r, g, b = (pixel>>11)&31, (pixel>>5)&63, pixel&31
        j = i//2*3
        rgb[j:j+3] = bytes(((r<<3)|(r>>2), (g<<2)|(g>>4), (b<<3)|(b>>2)))
    image = Image.frombytes("RGB", (320,240), bytes(rgb))
    output = io.BytesIO(); image.save(output, format="PNG")
    qr = []
    try:
        import cv2
        import numpy as np
        # OpenCV sees one fixed-size image; QR contents never become URLs/actions.
        value, _, _ = cv2.QRCodeDetector().detectAndDecode(np.array(image))
        if value: qr = [value[:2048]]
    except (ImportError, UnicodeError):
        pass
    except Exception as exc:
        if not isinstance(exc, cv2.error): raise
    return output.getvalue(), qr


from .vision_provider import describe_image, VisionServiceError


class DeskVision:
    def __init__(self, emit=None, source_device="robot-camera"):
        self.emit = emit or (lambda name, data: None)
        self.guard = lambda: None
        self.source_device = source_device
        self.width, self.height = 320, 240
        self.generation = 0
        self.png: bytes | None = None
        self.qr: list[str] = []
        self.description = ""
        self.question = ""
        self.captured = 0.0
        self.description_state = "idle"
        self.description_error = ""
        self._description_task = None

    async def accept(self, raw: bytes):
        self.png, self.qr = await asyncio.to_thread(decode_image, raw)
        self.source_device = "robot-camera"
        self.width, self.height = 320, 240
        self.generation += 1
        self.description = ""
        self.question = ""
        self.captured = time.time()
        self.description_state, self.description_error = "captured", ""
        self.publish()

    async def accept_jpeg(self, jpeg: bytes, generation: int):
        def decode():
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
                if len(png) > 700 * 1024:
                    raise ValueError("UnitV2 preview exceeds desktop transfer limit.")
                return png, image.size
        png, (width, height) = await asyncio.to_thread(decode)
        if self.generation != generation:
            raise RuntimeError("Image was cleared or replaced during capture. Capture again.")
        self.png, self.qr = png, []
        self.source_device = "unitv2-camera"
        self.width, self.height = width, height
        self.description = self.question = ""
        self.captured = time.time()
        self.description_state, self.description_error = "captured", ""
        self.generation += 1
        self.publish()

    def accept_frame(self, frame):
        self.guard()
        self.png, self.qr = frame.png, list(frame.qr)
        self.width, self.height = frame.width, frame.height
        self.source_device, self.captured = frame.source, frame.captured_at
        self.description = self.question = ""
        self.description_state, self.description_error = "captured", ""
        self.generation += 1
        self.publish()

    def publish(self):
        self.emit("snapshot", {"png": base64.b64encode(self.png).decode("ascii") if self.png else "",
            "source_device": self.source_device, "width": self.width, "height": self.height,
            "qr": self.qr, "description": self.description, "captured": self.captured, "retained": False,
            "description_state": self.description_state, "description_error": self.description_error})

    def clear(self):
        task = self._description_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        self.generation += 1
        self.png = None; self.qr = []; self.description = ""; self.question = ""; self.captured = 0
        self.description_state, self.description_error = "idle", ""
        self.publish()

    async def describe(self, question: str, settings):
        self.guard()
        if self.png is None: raise ValueError("Capture an image first.")
        if self._description_task is not None and not self._description_task.done():
            raise RuntimeError("A description is already in progress. Cancel it before starting another.")
        self._description_task = asyncio.current_task()
        image = self.png
        generation = self.generation
        self.description = self.description_error = ""
        self.description_state = "describing"
        self.publish()
        started = time.monotonic()
        status = {"state": "describing", "source_device": self.source_device}
        self.emit("vision_description", dict(status))
        try:
            reply = await describe_image(image, question, settings)
            self.guard()
            if self.png is not image or self.generation != generation:
                raise RuntimeError("Image changed during description. Capture again.")
        except BaseException as exc:
            reason = exc.reason if isinstance(exc, VisionServiceError) else "interrupted"
            status.update(state="cancelled" if reason == "interrupted" else "failed", reason=reason,
                          elapsed_ms=round((time.monotonic()-started)*1000))
            if isinstance(exc, VisionServiceError) and exc.http_status is not None:
                status["http_status"] = exc.http_status
            self.emit("vision_description", status)
            if self.png is image and self.generation == generation:
                from .vision_provider import failure_message
                self.description_state = status["state"]
                self.description_error = failure_message(reason)
                self.publish()
            raise
        finally:
            self._description_task = None
        self.description = reply
        self.question = question.strip()
        self.description_state = "complete"
        self.emit("vision_description", {**status, "state": "complete", "chars": len(reply),
                  "elapsed_ms": round((time.monotonic()-started)*1000)})
        self.publish()
        return {"spoken": reply, "qr": self.qr, "source": "Gemini"}

    async def save(self, directory: Path | KadencePaths, store, project_id: int):
        self.guard()
        if self.png is None: raise ValueError("Capture an image first.")
        image, description, question, captured = self.png, self.description, self.question, self.captured
        width, height, source_device, qr = self.width, self.height, self.source_device, list(self.qr)
        projects = await store.call("project_list")
        if not any(p["id"] == project_id for p in projects): raise ValueError("Choose an existing project.")
        paths = directory if isinstance(directory, KadencePaths) else KadencePaths.for_root(directory)
        await asyncio.to_thread(paths.prepare)
        path, relative = paths.image_path(captured, uuid.uuid4().hex)
        digest = hashlib.sha256(image).hexdigest()
        self.guard()
        if self.png is not image: raise RuntimeError("Image changed before saving.")
        def persist():
            try:
                path.write_bytes(image)
                return store._call("observation_add", {"project_id": project_id, "path": relative,
                    "captured": captured, "width": width, "height": height, "size_bytes": len(image),
                    "sha256": digest, "source_device": source_device, "question": question,
                    "description": description[:1200], "qr": qr})
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        # Once the explicit save starts, settle the file and metadata transaction
        # together even if the UI closes. Failed metadata cannot strand a file.
        task = asyncio.create_task(asyncio.to_thread(persist))
        try: record = await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        return {"id": record["id"], "media_id": record["media_id"],
                "message": "Observation and image saved to the selected project."}
