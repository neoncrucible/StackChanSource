"""UnitV2 camera service, Python 3.8 / standard library only.

Runs the ORIGINAL, checksum-verified M5Stack camera_stream executable. Each
camera lease expires on this device, independently of the Windows host.
No image is written to disk. This stops the producer, not the board's power.
"""
import base64
from collections import OrderedDict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
import time
import uuid

API = 1
VERSION = "1.0.0"
CAMERA_SHA256 = "a2203a4700445ee62feec8e5c645cf6ae05211e01ba2153ce555519f62f20b92"
MAX_JPEG = 2 * 1024 * 1024
MAX_LINE = 4 * MAX_JPEG // 3 + 4096
LEASE_SECONDS = 30


class CameraError(Exception):
    def __init__(self, reason, status=409):
        self.reason, self.status = reason, status


class Producer:
    def __init__(self, command, cwd, *, clock=time.monotonic, popen=subprocess.Popen, foreign=lambda pid:False):
        self.command, self.cwd, self.clock, self.popen = command, cwd, clock, popen
        self.foreign = foreign
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.control = threading.Lock()
        self.process = self.reader = None
        self.lease = None
        self.expires = 0
        self.state = "STOPPED"
        self.reason = "boot"
        self.frame = None
        self.sequence = 0
        self.frame_at = 0
        self.starts = self.stops = self.expirations = 0
        self.revoked = OrderedDict()
        self.closed = threading.Event()

    def status(self):
        with self.lock:
            live = self.process is not None and self.process.poll() is None
            if self.foreign(self.process.pid if live else None):
                self.state, self.reason = "FAULT", "other_camera_producer"
            if self.process is not None and not live and self.state not in {"STOPPING", "STOPPED"}:
                self.state, self.reason = "FAULT", "producer_exited"
            return {"api": API, "version": VERSION, "state": self.state,
                    "producer_running": live, "stop_confirmed": self.process is None and self.state == "STOPPED",
                    "lease": self.lease, "lease_remaining_ms": max(0, int((self.expires-self.clock())*1000)) if self.lease else 0,
                    "sequence": self.sequence, "starts": self.starts, "stops": self.stops,
                    "expirations": self.expirations, "reason": self.reason,
                    "sensor_power": "unverified"}

    def _revoke(self, lease):
        if lease:
            self.revoked[lease] = self.clock()
            while len(self.revoked) > 128:
                self.revoked.popitem(last=False)

    def start(self, lease):
        if not isinstance(lease, str) or not re.fullmatch(r"[0-9a-f]{32}", lease):
            raise CameraError("invalid_lease", 400)
        with self.control, self.lock:
            if self.closed.is_set(): raise CameraError("service_stopping", 503)
            if self.foreign(self.process.pid if self.process else None): raise CameraError("other_camera_producer", 503)
            if lease in self.revoked: raise CameraError("lease_revoked")
            if self.process is not None:
                if self.lease != lease: raise CameraError("camera_owned")
                if self.process.poll() is not None: raise CameraError("producer_exited", 503)
                if self.clock() >= self.expires: raise CameraError("lease_expired")
                self.expires = self.clock() + LEASE_SECONDS
                return self.status()
            self.state, self.reason = "STARTING", "starting"
            self.frame = None
            try:
                self.process = self.popen(self.command, cwd=self.cwd, stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                          bufsize=65536, close_fds=True)
                self.lease, self.expires = lease, self.clock()+LEASE_SECONDS
                self.starts += 1
                self.reader = threading.Thread(target=self._read, args=(self.process,), daemon=True)
                self.reader.start()
                # Vendor UnitV2Framework system command: turn on JPEG transmission.
                self.process.stdin.write(b'_{"stream":1}\r\n')
                self.process.stdin.flush()
            except Exception:
                self.state, self.reason = "FAULT", "start_failed"
                raise CameraError("start_failed", 503)
            return self.status()

    def _read(self, process):
        try:
            while True:
                line = process.stdout.readline(MAX_LINE+1)
                if not line: break
                if len(line) > MAX_LINE: raise ValueError("oversize")
                try: doc = json.loads(line)
                except (ValueError, UnicodeError): continue
                if not isinstance(doc, dict) or "img" not in doc: continue
                encoded = doc["img"]
                if not isinstance(encoded, str) or len(encoded) > 4*MAX_JPEG//3+4: raise ValueError("oversize")
                jpeg = base64.b64decode(encoded, validate=True)
                if not 4 <= len(jpeg) <= MAX_JPEG or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                    raise ValueError("invalid_image")
                with self.changed:
                    if self.process is not process or self.state == "STOPPING": return
                    self.frame, self.frame_at = jpeg, self.clock()
                    self.sequence += 1
                    self.state, self.reason = "RUNNING", "frame_ready"
                    self.changed.notify_all()
        except Exception:
            pass
        finally:
            with self.changed:
                if self.process is process and self.state != "STOPPING":
                    self.frame = None
                    self.state, self.reason = "FAULT", "producer_stream_ended"
                self.changed.notify_all()

    def snapshot(self, lease, timeout=8):
        with self.changed:
            if self.lease != lease or not lease: raise CameraError("lease_mismatch")
            if self.clock() >= self.expires: raise CameraError("lease_expired")
            self.expires = self.clock() + LEASE_SECONDS
            after, deadline = self.sequence, self.clock()+timeout
            while True:
                if self.lease != lease or self.state in {"STOPPING", "STOPPED", "FAULT"}:
                    raise CameraError("capture_cancelled", 503)
                if self.frame is not None and self.sequence > after and self.clock()-self.frame_at < 1:
                    return self.frame, self.sequence
                left = deadline-self.clock()
                if left <= 0: raise CameraError("frame_timeout", 504)
                self.changed.wait(min(left, .25))

    def stop(self, lease=None, reason="requested"):
        with self.control:
            with self.changed:
                if lease and self.lease and lease != self.lease: raise CameraError("lease_mismatch")
                self._revoke(lease or self.lease)
                process, reader = self.process, self.reader
                self.state, self.reason = "STOPPING", reason
                self.frame = None
                self.lease = None
                self.expires = 0
                self.changed.notify_all()
            if process is not None:
                # Signal only the Popen child owned by this service. Never killall.
                try:
                    if process.poll() is None:
                        process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                    if reader: reader.join(timeout=2)
                    if reader and reader.is_alive(): raise RuntimeError("reader did not settle")
                    for pipe in (process.stdin, process.stdout):
                        if pipe: pipe.close()
                except Exception:
                    with self.lock:
                        self.state, self.reason = "FAULT", "stop_unconfirmed"
                    raise CameraError("stop_unconfirmed", 503)
            with self.lock:
                if process is not None: self.stops += 1
                if reason == "lease_expired": self.expirations += 1
                self.process = self.reader = None
                self.state = "STOPPED"
                result = self.status()
                if not result["stop_confirmed"]: raise CameraError("other_camera_producer", 503)
                return result

    def watchdog_once(self):
        with self.lock:
            expired = self.process is not None and (self.clock() >= self.expires or self.state == "FAULT")
            lease = self.lease
        if expired:
            try: self.stop(lease, "lease_expired")
            except CameraError: pass

    def watchdog(self):
        while not self.closed.wait(.25): self.watchdog_once()

    def close(self):
        self.closed.set()
        return self.stop(reason="service_stopping")


class CameraService:
    def __init__(self, producer, key, *, clock=time.monotonic):
        if not re.fullmatch(r"[0-9a-f]{64}", key): raise ValueError("Invalid pairing key")
        self.producer, self.key, self.clock = producer, bytes.fromhex(key), clock
        self.challenges = OrderedDict()
        self.lock = threading.Lock()

    def challenge(self):
        with self.lock:
            now = self.clock()
            self.challenges = OrderedDict((k,v) for k,v in self.challenges.items() if now-v < 10)
            if len(self.challenges) >= 32: raise CameraError("busy", 429)
            nonce = secrets.token_hex(16)
            self.challenges[nonce] = now
        return {"service": "kadence-unitv2", "api": API, "version": VERSION, "nonce": nonce}

    def authenticate(self, raw, signature):
        expected = hmac.new(self.key, raw, hashlib.sha256).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
            raise CameraError("pairing_required", 401)
        try: request = json.loads(raw)
        except (ValueError, UnicodeError): raise CameraError("invalid_request", 400)
        if not isinstance(request, dict) or not isinstance(request.get("nonce"), str): raise CameraError("invalid_request", 400)
        with self.lock:
            issued = self.challenges.pop(request["nonce"], None)
        if issued is None or self.clock()-issued >= 10: raise CameraError("challenge_expired", 401)
        if set(request)-{"nonce", "operation", "lease"}: raise CameraError("invalid_request", 400)
        return request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8

    def __init__(self, address, service):
        self.service = service
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try: super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()

    def handle_error(self, request, client_address):
        pass  # No URLs, request bodies, credentials or images in logs.


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, *args): pass

    def reply(self, value, status=200, sequence=None):
        jpeg = isinstance(value, bytes)
        payload = value if jpeg else json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "image/jpeg" if jpeg else "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if sequence is not None: self.send_header("X-Kadence-Sequence", str(sequence))
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_GET(self):
        try:
            if self.path == "/kadence/v1/challenge": self.reply(self.server.service.challenge())
            elif self.path == "/": self.reply({"service": "Kadence UnitV2", "message": "Use Kadence Vision to start or stop the camera. The factory service is backed up; use Restore UnitV2 to restore it."})
            else: self.reply({"error": "not_found"}, 404)
        except CameraError as exc: self.reply({"error": exc.reason}, exc.status)

    def do_POST(self):
        try:
            if self.path != "/kadence/v1/control": raise CameraError("not_found", 404)
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or not 0 < int(length) <= 4096 or self.headers.get("Transfer-Encoding"):
                raise CameraError("invalid_request", 400)
            raw = self.rfile.read(int(length))
            if len(raw) != int(length): raise CameraError("invalid_request", 400)
            req = self.server.service.authenticate(raw, self.headers.get("X-Kadence-Signature"))
            operation, lease = req.get("operation"), req.get("lease")
            if lease is not None and (not isinstance(lease, str) or not re.fullmatch(r"[0-9a-f]{32}", lease)):
                raise CameraError("invalid_lease", 400)
            camera = self.server.service.producer
            if operation == "status": self.reply(camera.status())
            elif operation == "start": self.reply(camera.start(lease))
            elif operation == "stop": self.reply(camera.stop(lease))
            elif operation == "frame":
                jpeg, sequence = camera.snapshot(lease)
                self.reply(jpeg, sequence=sequence)
            else: raise CameraError("invalid_operation", 400)
        except CameraError as exc: self.reply({"error": exc.reason}, exc.status)


def main():
    root = Path(__file__).resolve().parent
    binary = root / "bin" / "camera_stream"
    if hashlib.sha256(binary.read_bytes()).hexdigest() != CAMERA_SHA256:
        raise RuntimeError("Camera executable differs from the verified factory image")
    key = (root / "kadence-camera.key").read_text().strip()
    def foreign(owned):
        # A factory supervisor restart can leave an old camera child behind.
        # Report the conflict; never claim it stopped or signal an unowned PID.
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) == owned: continue
            try:
                if (entry/"exe").resolve() == binary: return True
            except (FileNotFoundError, PermissionError, OSError): continue
        return False
    producer = Producer([str(binary)], str(root), foreign=foreign)
    service = CameraService(producer, key)
    server = Server(("0.0.0.0", 80), service)
    watcher = threading.Thread(target=producer.watchdog, daemon=True)
    watcher.start()
    def stop(signum, frame): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try: server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt: pass
    finally:
        producer.close()
        server.server_close()


if __name__ == "__main__": main()
