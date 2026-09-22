"""Bounded event-driven perception. ToF occupancy is never person identity."""
from __future__ import annotations
import asyncio
from collections import deque
import contextlib
from dataclasses import asdict
import hashlib
import json
import time
from .camera_manager import settled_thread
from .local_faces import LocalFaces, match, similarity
from .perception_store import PerceptionStore


class Occupancy:
    def __init__(self):
        self.state = "UNKNOWN"
        self.health = "unavailable"
        self.sequence = None
        self.since = 0.0
        self.last_sample = None
        self.distance = None

    def update(self, sample, now):
        before = self.state
        if sample is None or not sample.fresh or not sample.valid:
            self.state, self.health = "UNKNOWN", "unavailable" if sample is None else "invalid_or_stale"
            self.since = now
            self.distance = None
            return before != self.state
        if self.last_sample is not None and now-self.last_sample > 4:
            self.state = "UNKNOWN"
            self.since = now
        if self.sequence is not None and sample.sequence < self.sequence:
            self.state = "UNKNOWN"
            self.since = now
        if sample.sequence == self.sequence:
            if self.last_sample is not None and now-self.last_sample > 3:
                self.state, self.health = "UNKNOWN", "stale"
            return before != self.state
        self.sequence, self.last_sample = sample.sequence, now
        self.distance, self.health = sample.distance_mm, "ready"
        near, far = sample.distance_mm <= 900, sample.distance_mm >= 1200
        if self.state == "UNKNOWN":
            if near: self.state, self.since = "ARRIVAL_CANDIDATE", now
            elif far: self.state, self.since = "DEPARTURE_CANDIDATE", now
        elif self.state in {"CLEAR", "DEPARTURE_CANDIDATE"} and near:
            self.state, self.since = "ARRIVAL_CANDIDATE", now
        elif self.state in {"OCCUPIED", "ARRIVAL_CANDIDATE"} and far:
            self.state, self.since = "DEPARTURE_CANDIDATE", now
        elif self.state == "ARRIVAL_CANDIDATE" and near and now-self.since >= 2:
            self.state = "OCCUPIED"
        elif self.state == "DEPARTURE_CANDIDATE" and far and now-self.since >= 4:
            self.state = "CLEAR"
        return before != self.state


class CaptureBudget:
    def __init__(self): self.requests, self.last = deque(), -1e9
    def reserve(self, now):
        while self.requests and self.requests[0] <= now-60: self.requests.popleft()
        if now-self.last < 20 or len(self.requests)+2 > 6: return False
        self.requests.extend((now,now)); self.last = now
        return True


class PerceptionController:
    def __init__(self, camera, paths, emit, deliver, busy, *, faces=None, clock=time.monotonic):
        self.camera, self.paths, self.emit = camera, paths, emit
        self.deliver, self.busy, self.clock = deliver, busy, clock
        self.faces = faces or LocalFaces(paths.root)
        self.store = PerceptionStore(paths.database)
        self.occupancy, self.budget = Occupancy(), CaptureBudget()
        self.run = None
        self.task = None
        self._ticker = None
        self._last_tick = self.clock()
        self._last_expire = 0
        self._gesture_seq = None
        self._body_id = None
        self._tracks = []
        self._last_status = None
        self._last_failure = None
        self._enrolling = False
        self.subjects = 0
        self.health = "idle"
        self._closing = False

    async def db(self, operation, **args):
        return await settled_thread(lambda: self.store.call(operation, **args))

    async def start(self):
        await self.reset("startup")
        self._ticker = asyncio.create_task(self._tick_loop(), name="kadence-perception-clock")
        self.publish()

    async def interrupt(self):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task

    async def reset(self, reason):
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
        if self.run: await self.db("end", run=self.run, reason=reason)
        fingerprint = hashlib.sha256(json.dumps(asdict(self.camera.config),sort_keys=True).encode()).hexdigest()
        self.run = await self.db("begin", fingerprint=fingerprint)
        self._tracks.clear()
        self.subjects = 0
        self.occupancy = Occupancy()
        self._gesture_seq = None
        self.health = "idle"
        self.publish()

    async def close(self):
        if self._closing: return
        self._closing = True
        if self._ticker:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self._ticker
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
        if self.run:
            await self.db("end", run=self.run, reason="stopped")
            self.run = None

    async def _tick_loop(self):
        while True:
            await asyncio.sleep(1)
            try: await self.tick()
            except asyncio.CancelledError: raise
            except Exception:
                self.health = "storage_unavailable"
                self.publish()

    async def tick(self):
        now = self.clock()
        if now-self._last_tick > 15: await self.reset("resume")
        self._last_tick = now
        if self.occupancy.last_sample is not None and now-self.occupancy.last_sample > 4:
            self.occupancy.update(None,now)
        if now-self._last_expire > 10 and self.run:
            await self.db("expire", run=self.run, cutoff=time.time()-180)
            self._tracks = [t for t in self._tracks if now-t["seen"] <= 180]
            self.subjects = len(self._tracks)
            self._last_expire = now
        if self.camera.config.policy == "AWARE" and self.occupancy.state == "OCCUPIED" and now-self.budget.last >= 120:
            self.request("heartbeat")
        self.publish()

    async def sample(self, tof, gesture=None, body_id=None):
        if self._closing or not self.run: return
        if self._body_id is not None and self._body_id != body_id: await self.reset("device_reconnected")
        self._body_id = body_id
        changed = self.occupancy.update(tof,self.clock())
        if changed and self.occupancy.state in {"OCCUPIED", "CLEAR", "UNKNOWN"}:
            await self.db("event",run=self.run,kind="occupancy",trigger="tof",evidence={"state":self.occupancy.state})
        if changed and self.occupancy.state == "OCCUPIED": self.request("arrival")
        if changed and self.occupancy.state == "CLEAR":
            if self.task and not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
            await self.db("expire",run=self.run,cutoff=float("inf"),reason="zone_clear")
            self._tracks.clear(); self.subjects = 0
        if gesture and gesture.fresh:
            if self._gesture_seq is None: self._gesture_seq = gesture.event_sequence
            elif gesture.event_sequence < self._gesture_seq: self._gesture_seq = gesture.event_sequence
            elif gesture.event_sequence != self._gesture_seq:
                self._gesture_seq = gesture.event_sequence
                if gesture.event_age_ms <= 1500 and gesture.flags: self.request("gesture")
        self.publish()

    def request(self, trigger):
        if self._closing or self._enrolling or self.camera.config.privacy or self.camera.config.policy == "OFF" or self.busy(): return False
        if self.task and not self.task.done(): return False
        if not self.budget.reserve(self.clock()): return False
        self.task = asyncio.create_task(self._burst(trigger), name="kadence-perception")
        return True

    async def _burst(self, trigger):
        generation = self.camera.generation
        try:
            profiles = await self.db("profiles")
            candidates = []
            for index in range(2):
                if index: await asyncio.sleep(.8)
                self.camera.check(generation)
                if self.busy() or self.occupancy.state == "CLEAR": return
                frame = await self.camera.acquire(purpose="automatic")
                self.health = "processing"; self.publish()
                faces = await settled_thread(self.faces.analyze,frame.png)
                self.camera.check(generation)
                if index == 0:
                    candidates = [(face,match(face.embedding,profiles)) for face in faces]
                    continue
                used = set()
                present = []
                for face in faces:
                    person, status = match(face.embedding,profiles)
                    # Confirm across independent frames by embedding, not face count or position.
                    matches = [(similarity(face.embedding,old.embedding),i,old_result) for i,(old,old_result) in enumerate(candidates) if i not in used]
                    matches.sort(reverse=True)
                    if not matches or matches[0][0] < .65: continue
                    _, candidate, prior = matches[0]
                    used.add(candidate)
                    confirmed = person if person and prior[0] == person else None
                    if confirmed and any(t["person"] == confirmed for t in present): continue
                    existing = next((t for t in self._tracks if confirmed and t["person"] == confirmed),None)
                    if not confirmed:
                        # Unknown continuity is short and visual; never reuse a global unknown token.
                        used_sessions = {t["session"] for t in present}
                        possible = sorted(((similarity(t["embedding"],face.embedding),t) for t in self._tracks
                            if t["person"] is None and self.clock()-t["seen"] < 10 and t["session"] not in used_sessions), key=lambda item:item[0], reverse=True)
                        existing = possible[0][1] if possible and possible[0][0] >= .7 and (len(possible)==1 or possible[0][0]-possible[1][0]>=.08) else None
                    action = "greeting" if confirmed and self.camera.config.greetings else "unknown_alert" if not confirmed and self.camera.config.unknown_alerts else None
                    session = await self.db("observe",run=self.run,person=confirmed,frame=frame,trigger=trigger,
                        session=existing["session"] if existing else None,identity="ambiguous" if status=="ambiguous" else "unresolved",action=action)
                    self.camera.check(generation)
                    present.append({"session":session,"person":confirmed,"embedding":face.embedding,"seen":self.clock()})
                # Old evidence may survive briefly as 'temporarily lost', but is never refreshed by ToF.
                sessions = {t["session"] for t in present}
                self._tracks = present + [t for t in self._tracks if t["session"] not in sessions and self.clock()-t["seen"] < 180]
                self.subjects = len(present)
            self._last_failure = None
            self.health = "ready"
            await self.dispatch(generation)
        except asyncio.CancelledError: raise
        except Exception:
            self.health = self.faces.health if self.faces.health in {"models_missing","models_invalid"} else "unavailable"
            if self._last_failure != self.health:
                self._last_failure = self.health
                with contextlib.suppress(Exception):
                    await self.db("event",run=self.run,kind="recognition_unavailable" if self.health.startswith("models_") else "capture_failed",trigger=trigger,evidence={"health":self.health})
        finally: self.publish()

    async def dispatch(self, generation):
        if self.busy(): return
        self.camera.check(generation)
        if self.camera.config.policy == "OFF": return
        action = await self.db("claim",run=self.run,greetings=self.camera.config.greetings,unknown_alerts=self.camera.config.unknown_alerts)
        if not action: return
        outcome = "uncertain"
        try:
            self.camera.check(generation)
            if self.busy() or time.time() > action["expires_at"]:
                outcome = "suppressed"
            else:
                await self.deliver(action, lambda: self.camera.check(generation))
                outcome = "delivered"
        except asyncio.CancelledError: raise
        except Exception: outcome = "uncertain"
        finally: await self.db("complete",action=action["id"],state=outcome)

    async def enroll(self, name):
        if self._enrolling: raise RuntimeError("Enrollment is already running.")
        self.camera.check()
        self._enrolling = True
        generation = self.camera.generation
        vectors = []
        try:
            if self.task and not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError): await self.task
            for index in range(3):
                self.emit("enrollment", {"sample":index+1,"total":3})
                if index: await asyncio.sleep(1)
                frame = await self.camera.acquire(purpose="enrollment")
                faces = await settled_thread(self.faces.analyze,frame.png)
                self.camera.check(generation)
                if len(faces) != 1: raise RuntimeError("Enrollment needs exactly one clear face. Face the camera in good light and retry.")
                vector = faces[0].embedding
                if vectors and similarity(vectors[0],vector) < .65: raise RuntimeError("Face samples did not agree. Keep one person in view and retry.")
                vectors.append(vector)
            self.camera.check(generation)
            await self.db("enroll",name=name,vectors=vectors)
            return {"message":"Three local face samples enrolled. No images were saved.","persons":await self.db("persons")}
        finally:
            self._enrolling = False
            vectors.clear()
            self.publish()

    def publish(self):
        data = {"occupancy":self.occupancy.state,"sensor_health":self.occupancy.health,
            "distance_mm":self.occupancy.distance,"health":self.health,"model_health":self.faces.health,
            "subjects":self.subjects,"confirmed_persons":[t["person"] for t in self._tracks if t["person"]],"policy":self.camera.config.policy,"privacy":self.camera.config.privacy}
        if data != self._last_status:
            self._last_status = data
            self.emit("perception",data)
