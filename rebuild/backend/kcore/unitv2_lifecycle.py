"""Authenticated, bounded UnitV2 producer ownership for CameraManager."""
from __future__ import annotations
import asyncio
import contextlib
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
from pathlib import Path
import re
import select
import socket
import sys
import threading
import time
import uuid

STATES = frozenset({"STOPPED", "STARTING", "RUNNING", "STOPPING", "FAULT"})
MAX_JPEG = 2*1024*1024


def diagnostic_status(value):
    if not isinstance(value, dict) or value.get("mode") not in {"ON_DEMAND", "KEEP_READY", "STOPPED"}: return None
    if value.get("state") not in STATES | {"UNKNOWN", "UNAVAILABLE", "SETUP_REQUIRED", "STOP_UNCONFIRMED"}: return None
    safe={"mode":value["mode"], "state":value["state"]}
    for field in ("stop_confirmed", "producer_running"):
        if type(value.get(field)) is bool: safe[field]=value[field]
    for field in ("sequence", "starts", "stops", "expirations", "lease_remaining_ms"):
        item=value.get(field)
        if type(item) is int and 0 <= item <= 10**12: safe[field]=item
    return safe


def pairing_vault():
    from .credential_vault import CredentialVault
    return CredentialVault("Kadence/UnitV2/Camera", keys={"unitv2_token"})


def load_key():
    import os
    if os.name != "nt": return None
    key = pairing_vault().load().get("unitv2_token")
    if key is not None and not re.fullmatch(r"[0-9a-f]{64}", key): raise RuntimeError("UnitV2 pairing is invalid. Run UnitV2 setup.")
    return key


class LifecycleError(RuntimeError): pass


class _ResponseReader(io.RawIOBase):
    """Poll cancellation during headers and body; Windows shutdown cannot wake every read."""
    def __init__(self, connection, deadline, cancel):
        self.connection, self.deadline, self.cancel = connection, deadline, cancel
        connection.setblocking(False)

    def readable(self): return True

    def makefile(self, mode): return io.BufferedReader(self)

    def readinto(self, buffer):
        while True:
            if self.cancel and self.cancel.is_set(): raise LifecycleError("UnitV2 request cancelled")
            left = self.deadline-time.monotonic()
            if left <= 0: raise TimeoutError("UnitV2 deadline expired")
            ready, _, _ = select.select([self.connection], [], [], min(.1, left))
            if ready:
                try: return self.connection.recv_into(buffer)
                except BlockingIOError: continue


class Client:
    def __init__(self, address, key, *, port=80):
        self.address = str(ipaddress.IPv4Address(address))
        self.port, self.key = port, bytes.fromhex(key)
        self._socket = None
        if len(self.key) != 32: raise ValueError("Invalid UnitV2 pairing")

    def interrupt(self):
        active = self._socket
        if active is not None:
            with contextlib.suppress(OSError): active.shutdown(socket.SHUT_RDWR)

    def _http(self, method, path, deadline, *, body=None, signature=None, cancel=None):
        if cancel and cancel.is_set(): raise LifecycleError("UnitV2 request cancelled")
        remaining = deadline-time.monotonic()
        if remaining <= 0: raise TimeoutError("UnitV2 deadline expired")
        connection = http.client.HTTPConnection(self.address, self.port, timeout=min(2,remaining))
        response = None
        headers = {"Connection": "close"}
        if signature: headers.update({"Content-Type":"application/json", "X-Kadence-Signature":signature})
        try:
            connection.connect()
            self._socket = connection.sock
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise TimeoutError("UnitV2 deadline expired")
            self._socket.settimeout(remaining)
            if cancel and cancel.is_set(): raise LifecycleError("UnitV2 request cancelled")
            connection.request(method, path, body=body, headers=headers)
            # Retain the stdlib HTTP parser, but use interruptible reads rather
            # than its blocking socket.makefile. Each connection serves one request.
            response = http.client.HTTPResponse(_ResponseReader(self._socket, deadline, cancel), method=method)
            response.begin()
            length = response.getheader("Content-Length", "")
            jpeg = response.getheader("Content-Type", "").split(";")[0].strip() == "image/jpeg"
            if not length.isdigit() or not 0 < int(length) <= (MAX_JPEG if jpeg else 8192):
                raise LifecycleError("Invalid UnitV2 service response")
            data = bytearray()
            while len(data) < int(length):
                if cancel and cancel.is_set(): raise LifecycleError("UnitV2 request cancelled")
                left = deadline-time.monotonic()
                if left <= 0: raise TimeoutError("UnitV2 deadline expired")
                chunk = response.read(min(65536, int(length)-len(data)))
                if not chunk: raise LifecycleError("Truncated UnitV2 response")
                data.extend(chunk)
            if response.status != 200:
                if response.status == 401: raise LifecycleError("UnitV2 pairing rejected. Run UnitV2 setup again.")
                if response.status in {404, 410}: raise LifecycleError("UnitV2 lifecycle service is not installed. Run UnitV2 setup and power-cycle the camera.")
                raise LifecycleError("UnitV2 lifecycle request failed; check status and retry.")
            if jpeg:
                sequence = response.getheader("X-Kadence-Sequence", "")
                if not sequence.isdigit() or int(sequence) < 1: raise LifecycleError("UnitV2 frame sequence is missing")
                return bytes(data), int(sequence)
            value = json.loads(data)
            if not isinstance(value, dict): raise LifecycleError("Invalid UnitV2 service response")
            return value
        finally:
            self._socket = None
            if response is not None: response.close()
            connection.close()

    def call(self, operation, lease=None, *, timeout=5, cancel=None):
        deadline = time.monotonic()+timeout
        challenge = self._http("GET", "/kadence/v1/challenge", deadline, cancel=cancel)
        if (not isinstance(challenge, dict) or challenge.get("service") != "kadence-unitv2" or challenge.get("api") != 1
                or not isinstance(challenge.get("nonce"), str) or not re.fullmatch(r"[0-9a-f]{32}", challenge["nonce"])):
            raise LifecycleError("UnitV2 lifecycle service is not compatible")
        data = {"operation":operation, "nonce":challenge["nonce"]}
        if lease is not None: data["lease"] = lease
        body = json.dumps(data, separators=(",", ":")).encode()
        signature = hmac.new(self.key, body, hashlib.sha256).hexdigest()
        result = self._http("POST", "/kadence/v1/control", deadline, body=body, signature=signature, cancel=cancel)
        if operation == "frame":
            if not isinstance(result, tuple): raise LifecycleError("UnitV2 returned no image")
            return result
        if not isinstance(result, dict) or result.get("api") != 1 or result.get("state") not in STATES:
            raise LifecycleError("Invalid UnitV2 lifecycle status")
        for name in ("producer_running", "stop_confirmed"):
            if type(result.get(name)) is not bool: raise LifecycleError("Invalid UnitV2 lifecycle status")
        if operation == "stop" and (result["state"] != "STOPPED" or not result["stop_confirmed"] or result["producer_running"]):
            raise LifecycleError("UnitV2 producer stop was not confirmed")
        return result


class UnitV2Owner:
    """All network workers settle before releasing ownership, including cancellation."""
    def __init__(self, emit, *, key_loader=load_key, client_factory=Client):
        self.emit, self.key_loader, self.client_factory = emit, key_loader, client_factory
        self.client = None
        self.lease = None
        self.sequence = 0
        self.status = {"state":"UNKNOWN", "stop_confirmed":False, "producer_running":False}
        self.mode = "ON_DEMAND"
        self.lock = asyncio.Lock()
        self.heartbeat = None
        self.closed = False
        self._holds = set()
        self._cancel_epoch = 0
        self.verification_root = None
        self.verified = False

    def publish(self, result=None):
        if result is not None: self.status = result
        data = {"mode":self.mode, "state":self.status.get("state", "UNKNOWN"),
                "stop_confirmed":self.status.get("stop_confirmed") is True,
                "producer_running":self.status.get("producer_running") is True,
                "verified":self.verified,
                "sensor_power":"unverified"}
        for field in ("sequence", "starts", "stops", "expirations", "lease_remaining_ms"):
            value = self.status.get(field)
            if type(value) is int and 0 <= value <= 10**12: data[field] = value
        self.emit("unitv2_lifecycle", data)
        return data

    async def _call(self, operation, *, lease=None, timeout=5):
        from .camera_manager import settled_thread
        cancelled=threading.Event()
        def interrupt():
            cancelled.set()
            self.client.interrupt()
        result = await settled_thread(lambda:self.client.call(operation, lease, timeout=timeout, cancel=cancelled),on_cancel=interrupt)
        if operation != "frame": self.publish(result)
        return result

    async def _select(self, address):
        if self.client and self.client.address == address: return True
        if self.client:
            with contextlib.suppress(Exception): await self._stop()
            self.client = None
        key = self.key_loader()
        if not key:
            self.verified = False
            self.publish({"state":"SETUP_REQUIRED", "stop_confirmed":False})
            return False
        self.client = self.client_factory(address, key)
        self.verified = False
        if self.verification_root:
            try:
                data=json.loads((Path(self.verification_root)/"unitv2-verification.json").read_text())
                self.verified=data=={"format":1,"service_version":"1.0.0","key_id":hashlib.sha256(bytes.fromhex(key)).hexdigest()}
            except (ValueError,OSError,TypeError): pass
        self.sequence = 0
        return True

    async def _stop(self, *, all_leases=False):
        if not self.client: return
        lease = self.lease
        self.lease = None
        try:
            await self._call("stop", lease=None if all_leases else lease, timeout=7)
        except BaseException:
            self.publish({"state":"STOP_UNCONFIRMED", "stop_confirmed":False})
            raise

    async def _start(self):
        if self.closed: raise LifecycleError("Camera owner is closed")
        if self.lease is None:
            self.lease, self.sequence = uuid.uuid4().hex, 0
        await self._call("start", lease=self.lease)

    async def capture(self, address, *, timeout=12):
        from .camera_manager import decode_jpeg, settled_thread
        async with self.lock:
            if not await self._select(address): return None  # Legacy manual path.
            epoch = self._cancel_epoch
            succeeded = False
            try:
                await self._start()
                jpeg, sequence = await self._call("frame", lease=self.lease, timeout=max(1,min(10,timeout-2)))
                if sequence <= self.sequence: raise LifecycleError("UnitV2 repeated an old frame")
                self.sequence = sequence
                decoded = await settled_thread(decode_jpeg, jpeg)
                self.publish({**self.status, "state":"RUNNING", "producer_running":True, "stop_confirmed":False, "sequence":sequence})
                succeeded = True
                return decoded
            finally:
                if (self.mode != "KEEP_READY" and not self._holds) or epoch != self._cancel_epoch or not succeeded:
                    # A shield alone is insufficient: wait for the stop worker to finish.
                    cancelled = isinstance(sys.exception(), asyncio.CancelledError)
                    try: await settled_thread(self._stop_sync)
                    except Exception:
                        if not cancelled: raise
                    finally: self.publish()

    def _stop_sync(self):
        # Called while lock is retained; publication stays on the event loop.
        lease, self.lease = self.lease, None
        try: result = self.client.call("stop", lease, timeout=7)
        except Exception:
            self.status = {"state":"STOP_UNCONFIRMED", "stop_confirmed":False}
            raise
        self.status = result

    def revoke(self):
        self._cancel_epoch += 1

    async def control_mode(self, mode, address):
        if mode not in {"ON_DEMAND", "KEEP_READY", "STOPPED"}: raise ValueError("Choose a supported camera mode")
        self.revoke()
        epoch = self._cancel_epoch
        self.mode = mode
        if self.heartbeat:
            self.heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.heartbeat
            self.heartbeat = None
        async with self.lock:
            if not await self._select(address): raise LifecycleError("Run UnitV2 setup once to enable start/stop control.")
            await self._stop(all_leases=True)
            if mode == "KEEP_READY":
                if epoch != self._cancel_epoch: raise LifecycleError("Camera start was superseded")
                await self._start()
                if epoch != self._cancel_epoch:
                    await self._stop()
                    raise LifecycleError("Camera start was superseded")
                try:
                    from .camera_manager import decode_jpeg, settled_thread
                    jpeg, sequence = await self._call("frame", lease=self.lease, timeout=10)
                    await settled_thread(decode_jpeg, jpeg)
                    if epoch != self._cancel_epoch: raise LifecycleError("Camera start was superseded")
                    self.sequence = sequence
                    self.publish({**self.status,"state":"RUNNING","producer_running":True,"stop_confirmed":False,"sequence":sequence})
                except BaseException:
                    await self._stop()
                    raise
                self.heartbeat = asyncio.create_task(self._renew(), name="kadence-camera-lease")
        self.publish()

    def record_verified(self, root):
        if not self.client or not self.status.get("stop_confirmed") or self.status.get("version") != "1.0.0":
            raise LifecycleError("Camera lifecycle verification did not complete")
        path=Path(root)/"unitv2-verification.json"
        data={"format":1,"service_version":"1.0.0","key_id":hashlib.sha256(self.client.key).hexdigest()}
        temp=path.with_suffix(".tmp")
        temp.write_text(json.dumps(data),encoding="utf-8");temp.replace(path)
        self.verification_root=root
        self.verified=True
        self.publish()

    async def refresh(self, address):
        async with self.lock:
            if not await self._select(address): return self.publish()
            try: await self._call("status")
            except Exception:
                self.publish({"state":"UNAVAILABLE", "stop_confirmed":False})
                raise
        return self.publish()

    async def _renew(self):
        try:
            while True:
                await asyncio.sleep(8)
                async with self.lock:
                    if self.mode != "KEEP_READY" or not self.lease: return
                    await self._call("start", lease=self.lease)
        except asyncio.CancelledError: raise
        except Exception:
            self.mode = "STOPPED"
            self.publish({"state":"STOP_UNCONFIRMED", "stop_confirmed":False})
            with contextlib.suppress(Exception):
                async with self.lock: await self._stop()

    @contextlib.asynccontextmanager
    async def burst(self):
        token = uuid.uuid4().hex
        self._holds.add(token)
        try: yield
        finally:
            cancelled=isinstance(sys.exception(),asyncio.CancelledError)
            self._holds.discard(token)
            async with self.lock:
                if self.client and self.mode != "KEEP_READY" and not self._holds and self.lease:
                    try: await self._stop()
                    except Exception:
                        if not cancelled: raise

    async def stop(self, address=None):
        self.revoke()
        self.mode = "STOPPED" if self.mode=="STOPPED" else "ON_DEMAND"
        if self.heartbeat:
            self.heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.heartbeat
            self.heartbeat = None
        async with self.lock:
            if address and not self.client: await self._select(address)
            if self.client: await self._stop(all_leases=True)
        self.publish()

    async def close(self):
        if self.closed: return
        self.closed = True
        await self.stop()
