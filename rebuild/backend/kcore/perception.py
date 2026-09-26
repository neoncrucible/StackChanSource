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
from .local_faces import LocalFaces, match, match_details, quality_message, similarity
from .face_media import preview, reference
from .perception_store import PerceptionStore


from .occupancy import Occupancy  # compatibility for callers of the existing tracker
from .sensor_sampler import SensorSampler, SensorObservation

TRIGGERS = frozenset({"arrival", "gesture", "close_approach", "heartbeat"})
REASONS = frozenset({"ready", "observation_only", "privacy", "policy_off", "stopped", "lifecycle_check_required",
    "voice_busy", "camera_busy", "enrolling", "zone_clear", "sensor_unknown", "cooldown", "expired", "session_changed",
    "captured", "cancelled", "unavailable", "storage_unavailable", "models_missing", "models_invalid", "low_salience"})


def diagnostic_decision(value):
    if not isinstance(value, dict) or value.get("trigger") not in TRIGGERS: return None
    if value.get("decision") not in {"accepted", "deferred", "suppressed", "completed", "failed", "cancelled"}: return None
    if value.get("reason") not in REASONS: return None
    return {key:value[key] for key in ("trigger", "decision", "reason")}


def diagnostic_state(value):
    allowed={"gate":REASONS,"health":{"idle","processing","ready","unavailable","storage_unavailable","models_missing","models_invalid"},
             "model_health":{"not_loaded","ready","models_missing","models_invalid"},
             "occupancy":{"UNKNOWN","CLEAR","ARRIVAL_CANDIDATE","OCCUPIED","DEPARTURE_CANDIDATE"},
             "sensor_health":{"ready","unavailable","invalid_or_stale","stale"},"policy":{"OFF","EVENT_ONLY","AWARE"}}
    safe={key:item for key,options in allowed.items() if isinstance(item:=value.get(key),str) and item in options}
    for key in ("bursts","completed_bursts","subjects","observed","temporarily_lost","ambiguous","last_capture_age_s"):
        item=value.get(key)
        if type(item) is int and 0 <= item <= 10**12: safe[key]=item
    if type(value.get("privacy")) is bool:safe["privacy"]=value["privacy"]
    return safe


class CaptureBudget:
    def __init__(self): self.requests, self.last = deque(), -1e9
    def delay(self, now):
        while self.requests and self.requests[0] <= now-60: self.requests.popleft()
        return max(0,self.last+20-now,self.requests[0]+60-now if len(self.requests)+2>6 else 0)
    def reserve(self, now):
        if self.delay(now)>0: return False
        self.requests.extend((now,now)); self.last = now
        return True


class PerceptionController:
    def __init__(self, camera, paths, emit, deliver, busy, *, faces=None, clock=time.monotonic, sampler=None):
        self.camera, self.paths, self.emit = camera, paths, emit
        self.deliver, self.busy, self.clock = deliver, busy, clock
        self.faces = faces or LocalFaces(paths.root)
        self.store = PerceptionStore(paths.database)
        self.sampler = sampler or SensorSampler(emit, clock=clock)
        self.budget = CaptureBudget()
        self.run = None
        self.task = None
        self._ticker = None
        self._last_tick = self.clock()
        self._last_expire = 0
        self._tracks = []
        self._last_status = None
        self._last_failure = None
        self._enrolling = False
        self.subjects = 0
        self.health = "idle"
        self._closing = False
        self.pending = None
        self._next_aware = self.clock()+120
        self._visit_greeted = set()
        self._unknown_notified = False
        self._last_capture = None
        self._burst_number = 0
        self._completed_bursts = 0
        self._decisions = deque(maxlen=32)
        self._reset_lock = asyncio.Lock()
        self._resetting = False
        self._explicit_task = None
        self.last_result = "No camera look has completed in this session."
        self.last_greeting = "No greeting attempted in this session."

    @property
    def occupancy(self):
        return self.sampler.occupancy

    async def db(self, operation, **args):
        return await settled_thread(lambda: self.store.call(operation, **args))

    async def start(self):
        await self.reset("startup")
        self._ticker = asyncio.create_task(self._tick_loop(), name="kadence-perception-clock")
        self.publish()

    async def interrupt(self):
        self.emit("face_preview",{})
        self.pending = None
        explicit = self._explicit_task
        if explicit and explicit is not asyncio.current_task() and not explicit.done():
            explicit.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await explicit
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task

    async def reset(self, reason):
        async with self._reset_lock:
            self._resetting = True
            try: await self._reset(reason)
            finally:
                self._resetting = False
                self.publish()

    async def _reset(self, reason):
        await self.interrupt()
        self.pending = None
        self._next_aware = self.clock()+120
        self._visit_greeted.clear()
        self._unknown_notified = False
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
        await self._flush_decisions()
        await self._record_reflex(self.sampler.reset(reason))
        if self.run: await self.db("end", run=self.run, reason=reason)
        fingerprint = hashlib.sha256(json.dumps(asdict(self.camera.config),sort_keys=True).encode()).hexdigest()
        self.run = await self.db("begin", fingerprint=fingerprint)
        self._tracks.clear()
        self.subjects = 0
        self.health = "idle"
        self.publish()

    async def close(self):
        if self._closing: return
        self._closing = True
        await self.interrupt()
        self.pending = None
        if self._ticker:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self._ticker
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
        if self.run:
            await self._flush_decisions()
            await self._record_reflex(self.sampler.reset("stopped"))
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
        if self._resetting or self._closing: return
        now = self.clock()
        if now-self._last_tick > 15: await self.reset("resume")
        self._last_tick = now
        if self.occupancy.last_sample is not None and now-self.occupancy.last_sample > 4 and self.occupancy.state != "UNKNOWN":
            await self.sample(self.sampler.sample(None))
        if now-self._last_expire > 10 and self.run:
            await self.db("expire", run=self.run, cutoff=time.time()-180)
            self._tracks = [t for t in self._tracks if now-t["seen"] <= 180]
            self.subjects = sum(t.get("observed",False) for t in self._tracks)
            self._last_expire = now
        if self.pending:
            pending = self.pending
            if now > pending["expires"]:
                self.pending = None
                self._decision(pending["trigger"], "suppressed", "expired")
            elif pending["generation"] != self.camera.generation or pending["session"] != self.sampler.reflex.session_id:
                self.pending = None
                self._decision(pending["trigger"], "suppressed", "session_changed")
            elif not self.busy() and not (self.task and not self.task.done()) and self.budget.delay(now)==0:
                self.pending = None
                self.request(pending["trigger"], defer=False)
        if self.camera.config.policy == "AWARE" and self.occupancy.state == "OCCUPIED" and now >= self._next_aware:
            self._next_aware = now+120
            self.request("heartbeat", defer=False)
        await self._flush_decisions()
        self.publish()

    async def _flush_decisions(self):
        run=self.run
        decisions=tuple(self._decisions)
        self._decisions.clear()
        if run:
            for decision in decisions:
                await self.db("event",run=run,kind="perception_decision",trigger=decision["trigger"],evidence=decision)

    async def _record_reflex(self, events):
        run = self.run
        if not run: return
        for event in events:
            await self.db("event", run=run, kind="reflex_proposed", trigger=event.type, evidence=event.payload())

    async def sample(self, observation: SensorObservation):
        """Receive upstream proposals; only this layer can request visual work."""
        if self._closing or self._resetting or not self.run: return
        await self._record_reflex(observation.events)
        if observation.changed and observation.occupancy in {"OCCUPIED", "CLEAR", "UNKNOWN"}:
            await self.db("event",run=self.run,kind="occupancy",trigger="tof",evidence={"state":observation.occupancy})
        if observation.changed and observation.occupancy == "CLEAR":
            self.pending = None
            self._visit_greeted.clear()
            self._unknown_notified = False
            if self.task and not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception): await self.task
            await self.db("expire",run=self.run,cutoff=float("inf"),reason="zone_clear")
            self._tracks.clear(); self.subjects = 0
        for event in observation.events:
            if event.perception_required and event.type in TRIGGERS:
                if event.salience >= .75 and event.confidence >= .6:
                    self.request(event.type)
                else: self._decision(event.type, "suppressed", "low_salience")
        self.publish()

    def gate(self):
        if self._closing or self._resetting: return "stopped"
        if self.camera.config.privacy: return "privacy"
        if not self.camera.config.perception_enabled: return "observation_only"
        if self.camera.config.policy == "OFF": return "policy_off"
        if self.camera.unitv2.mode == "STOPPED": return "stopped"
        if self.camera.config.source != "robot-camera" and not self.camera.unitv2.verified: return "lifecycle_check_required"
        if self._enrolling or (self._explicit_task and not self._explicit_task.done()): return "enrolling"
        return "ready"

    def _decision(self, trigger, decision, reason):
        item={"trigger":trigger,"decision":decision,"reason":reason}
        self._decisions.append(item)
        self.emit("perception_decision",item)

    def request(self, trigger, *, defer=True):
        if trigger not in TRIGGERS: return False
        reason=self.gate()
        if reason != "ready":
            # Quiet baseline: Gate 2 already records the proposals.
            if reason != "observation_only": self._decision(trigger,"suppressed",reason)
            return False
        if trigger != "gesture" and self.occupancy.state != "OCCUPIED":
            self._decision(trigger,"suppressed","zone_clear" if self.occupancy.state=="CLEAR" else "sensor_unknown")
            return False
        busy=self.busy() or self.camera._active is not None or (self.task and not self.task.done())
        if busy:
            reason="voice_busy" if self.busy() else "camera_busy"
            if defer and trigger != "heartbeat":
                priority={"arrival":3,"close_approach":2,"gesture":1}
                # One short-lived pending intent; repeated input cannot extend its life.
                if self.pending is None or priority[trigger] > priority[self.pending["trigger"]]:
                    self.pending={"trigger":trigger,"expires":self.clock()+(15 if trigger=="arrival" else 5),
                                  "generation":self.camera.generation,"session":self.sampler.reflex.session_id}
                    self._decision(trigger,"deferred",reason)
            else: self._decision(trigger,"suppressed",reason)
            return False
        if not self.budget.reserve(self.clock()):
            if defer and trigger=="arrival" and self.budget.delay(self.clock())<=15:
                self.pending={"trigger":trigger,"expires":self.clock()+15,"generation":self.camera.generation,
                              "session":self.sampler.reflex.session_id}
                self._decision(trigger,"deferred","cooldown")
                return False
            self._decision(trigger,"suppressed","cooldown")
            return False
        self._decision(trigger,"accepted","ready")
        self._next_aware=self.clock()+120
        self.task = asyncio.create_task(self._burst(trigger), name="kadence-perception")
        return True

    async def _burst(self, trigger):
        if trigger not in TRIGGERS: return
        generation=self.camera.generation
        try:
            async with self.camera.unitv2.burst():
                completed=await self._analyze_burst(trigger)
            if completed:
                self.camera.check(generation)
                self.health="ready"
                self._completed_bursts += 1
                self._decision(trigger,"completed","captured")
                # Release the camera before optional speech or notification.
                await self.dispatch(generation)
        except asyncio.CancelledError: raise
        except Exception:
            self.health="unavailable"
            self._decision(trigger,"failed","unavailable")
        finally: self.publish()

    async def _analyze_burst(self, trigger):
        generation = self.camera.generation
        try:
            if self.gate() != "ready": return
            self._burst_number += 1
            profiles = await self.db("profiles")
            candidates = []
            for index in range(2):
                if index: await asyncio.sleep(.8)
                self.camera.check(generation)
                if self.busy() or (self.occupancy.state == "CLEAR" and trigger != "gesture"): return
                frame = await self.camera.acquire(purpose="automatic")
                self.health = "processing"; self.publish()
                faces, report = await self._face_evidence(frame)
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
                    identity = "ambiguous" if status=="ambiguous" or prior[1]=="ambiguous" or (not confirmed and (person or prior[0])) else "unresolved"
                    if confirmed and any(t["person"] == confirmed for t in present): continue
                    existing = next((t for t in self._tracks if confirmed and t["person"] == confirmed),None)
                    if not confirmed:
                        # Unknown continuity is short and visual; never reuse a global unknown token.
                        used_sessions = {t["session"] for t in present}
                        possible = sorted(((similarity(t["embedding"],face.embedding),t) for t in self._tracks
                            if t["person"] is None and self.clock()-t["seen"] < 10 and t["session"] not in used_sessions), key=lambda item:item[0], reverse=True)
                        existing = possible[0][1] if possible and possible[0][0] >= .7 and (len(possible)==1 or possible[0][0]-possible[1][0]>=.08) else None
                    action = "greeting" if confirmed and self.camera.config.greetings and confirmed not in self._visit_greeted else "unknown_alert" if not confirmed and identity=="unresolved" and self.camera.config.unknown_alerts and not self._unknown_notified else None
                    session = await self.db("observe",run=self.run,person=confirmed,frame=frame,trigger=trigger,
                        session=existing["session"] if existing else None,identity=identity,action=action)
                    self.camera.check(generation)
                    present.append({"session":session,"person":confirmed,"identity":"confirmed" if confirmed else identity,"embedding":face.embedding,"seen":self.clock(),"observed":True})
                # Old evidence may survive briefly as 'temporarily lost', but is never refreshed by ToF.
                sessions = {t["session"] for t in present}
                self._tracks = present + [{**t,"observed":False} for t in self._tracks if t["session"] not in sessions and self.clock()-t["seen"] < 180]
                self.subjects = len(present)
            self._last_capture = self.clock()
            names = {p["id"]:p["display_name"] for p in await self.db("persons")}
            self.camera.check(generation)
            confirmed_names = [names[t["person"]] for t in self._tracks if t["observed"] and t["person"] in names]
            self.last_result = ("Recognised: " + ", ".join(confirmed_names) + ".") if confirmed_names else (quality_message(report) if not faces else f"{len(faces)} usable face(s), {self.subjects} stable across both frames; no enrolled identity confirmed.")
            self.emit("vision_activity", {"kind":"automatic_look","message":self.last_result,"source":frame.source})
            await self.db("event",run=self.run,kind="capture_result",trigger=trigger,frame=frame,
                          evidence={"frames":2,"subjects":self.subjects,"confirmed":sum(t["person"] is not None and t["observed"] for t in self._tracks)})
            del frame
            self._last_failure = None
            return True
        except asyncio.CancelledError:
            self.health = "idle"
            if trigger in TRIGGERS: self._decision(trigger,"cancelled","cancelled")
            raise
        except Exception:
            self.health = self.faces.health if self.faces.health in {"models_missing","models_invalid"} else "unavailable"
            self.last_result = "Camera look failed: " + self.health.replace('_',' ') + "."
            self.emit("vision_activity",{"kind":"automatic_look","message":self.last_result})
            if trigger in TRIGGERS: self._decision(trigger,"failed",self.health)
            if self._last_failure != self.health:
                self._last_failure = self.health
                with contextlib.suppress(Exception):
                    await self.db("event",run=self.run,kind="recognition_unavailable" if self.health.startswith("models_") else "capture_failed",trigger=trigger,evidence={"health":self.health})
        finally: self.publish()

    async def dispatch(self, generation):
        if self.gate() != "ready": return
        if self.busy(): return
        self.camera.check(generation)
        if self.camera.config.policy == "OFF": return
        action = await self.db("claim",run=self.run,greetings=self.camera.config.greetings,unknown_alerts=self.camera.config.unknown_alerts)
        if not action:
            present={t["person"] for t in self._tracks if t["person"] and t.get("observed")}
            if not self.camera.config.greetings: self.last_greeting = "Greetings are off."
            elif not present: self.last_greeting = "No greeting: no enrolled identity confirmed in this look."
            elif present <= self._visit_greeted: self.last_greeting = "No repeat greeting: already attempted during this visit."
            else: self.last_greeting = "No eligible greeting: check the profile's Greet switch, five-minute guard and recent evidence."
            self.emit("vision_activity",{"kind":"greeting","message":self.last_greeting})
            return
        if action["kind"] == "greeting": self._visit_greeted.add(action["person_id"])
        else: self._unknown_notified = True
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
        finally:
            await self.db("complete",action=action["id"],state=outcome)
            self.last_greeting = f"{action['kind'].replace('_',' ').capitalize()}: {outcome}."
            self.emit("vision_activity",{"kind":"greeting","message":self.last_greeting})

    async def _face_evidence(self, frame, *, show=False):
        detailed = getattr(self.faces,"analyze_details",None)
        if callable(detailed):
            faces,report = await settled_thread(detailed,frame.png)
        else:
            faces = await settled_thread(self.faces.analyze,frame.png)
            report = {"detected":len(faces),"usable":len(faces),"small":0,"blurred":0}
        self.camera.check(frame.generation)
        if show:
            try: encoded = await settled_thread(preview,frame.png,faces)
            except (ValueError,OSError): encoded = None
            self.camera.check(frame.generation)
            self.emit("face_preview",{"png_base64":encoded,"source":frame.source,"captured_at":frame.captured_at,"message":quality_message(report)})
        return faces,report

    async def enroll(self, name, person=None, *, keep_photos=False):
        if type(keep_photos) is not bool: raise ValueError("Choose whether to keep local review photos.")
        await self.interrupt()
        self._explicit_task = asyncio.current_task()
        try:
            async with self.camera.unitv2.burst():
                result = await self._enroll(name, person, keep_photos=keep_photos)
            self.emit("enrollment",{"state":"saved","message":result["message"],"sample":3,"total":3})
            return result
        except BaseException as exc:
            message = "Enrollment interrupted. Refresh Profiles to check the saved state." if isinstance(exc,asyncio.CancelledError) else str(exc) if type(exc) in {RuntimeError,ValueError} else "Enrollment failed. Check the camera and local face models."
            self.emit("enrollment",{"state":"failed","message":message})
            raise
        finally:
            self._explicit_task = None
            self.publish()

    async def _enroll(self, name, person=None, *, keep_photos=False):
        if self._enrolling: raise RuntimeError("Enrollment is already running.")
        self.camera.check()
        self._enrolling = True
        generation = self.camera.generation
        vectors = []
        references = []
        source = None
        try:
            if self.task and not self.task.done():
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError): await self.task
            for index in range(3):
                self.emit("enrollment", {"state":"capturing","sample":index+1,"total":3})
                if index: await asyncio.sleep(1)
                if self.busy(): raise RuntimeError("Voice is busy. Try enrollment after the reply finishes.")
                frame = await self.camera.acquire(purpose="enrollment")
                faces,report = await self._face_evidence(frame,show=True)
                self.camera.check(generation)
                if source is not None and source != frame.source: raise RuntimeError("Camera source changed during enrollment. Choose a specific camera and retry.")
                source = frame.source
                if not faces: raise RuntimeError(quality_message(report))
                if len(faces) != 1: raise RuntimeError("Multiple usable faces detected. Enrollment needs one person in view.")
                vector = faces[0].embedding
                if vectors and similarity(vectors[0],vector) < .65: raise RuntimeError("Face samples did not agree. Keep one person in view and retry.")
                vectors.append(vector)
                if keep_photos: references.append(await settled_thread(reference,frame,faces[0]))
                self.camera.check(generation)
                self.emit("enrollment", {"state":"accepted","sample":index+1,"total":3,"source":source})
            self.camera.check(generation)
            person = await self.db("enroll",name=name,vectors=vectors,person=person,references=references if keep_photos else None)
            photo_message = "3 local review photos saved; select the profile to view them." if keep_photos else "No photographs saved."
            return {"message":f"Saved: {name}. Three face samples from {source}. {photo_message}","person_id":person,"persons":await self.db("persons")}
        finally:
            self._enrolling = False
            vectors.clear()
            references.clear()
            self.publish()

    async def test_recognition(self):
        """Explicit, local two-frame check; never manufactures a visit or greeting."""
        await self.interrupt()
        self.camera.check()
        self._explicit_task = asyncio.current_task()
        self._enrolling = True
        generation = self.camera.generation
        try:
            profiles = await self.db("profiles")
            candidates = []
            confirmed = set()
            reports, match_reports = [], []
            agreement = False
            async with self.camera.unitv2.burst():
                for index in range(2):
                    if index: await asyncio.sleep(.8)
                    if self.busy(): raise RuntimeError("Voice is busy. Test recognition after the reply finishes.")
                    self.camera.check(generation)
                    self.emit("vision_activity",{"kind":"recognition_test","message":f"Checking frame {index+1}/2 locally…"})
                    frame = await self.camera.acquire(purpose="manual")
                    faces,report = await self._face_evidence(frame,show=True)
                    reports.append(report)
                    match_reports.append([match_details(face.embedding,profiles) for face in faces])
                    self.camera.check(generation)
                    if not index:
                        candidates = [(face,match(face.embedding,profiles)) for face in faces]
                        source = frame.source
                    else:
                        if frame.source != source: raise RuntimeError("Camera source changed between frames. Choose a specific camera and retry.")
                        used = set()
                        for face in faces:
                            person,status = match(face.embedding,profiles)
                            matches = sorted(((similarity(face.embedding,old.embedding),i,prior) for i,(old,prior) in enumerate(candidates) if i not in used),reverse=True)
                            if not matches or matches[0][0] < .65: continue
                            _,i,prior = matches[0]; used.add(i)
                            agreement = True
                            if person and prior[0] == person: confirmed.add(person)
            self.camera.check(generation)
            names = [p["display_name"] for p in await self.db("persons") if p["id"] in confirmed]
            self.camera.check(generation)
            message = "Recognised: " + ", ".join(names) + "." if names else "No enrolled identity confirmed."
            if not faces: message = quality_message(report)
            elif not profiles: message = "A face was seen, but there are no enabled compatible profiles. Enrol a profile first."
            elif not names:
                best = max(match_reports[-1],key=lambda item:item["score"] if item["score"] is not None else -1)
                if best["reason"] == "below_threshold": message += f" Best similarity {best['score']:.3f}; required {best['threshold']:.2f}. Try replacing samples from this camera."
                elif best["reason"] == "ambiguous": message += f" Profiles too similar: score gap {best['gap']:.3f}; required {best['margin']:.2f}."
                elif not agreement: message += " Faces did not agree across both frames. Hold still and retry."
                else: message += " The same profile was not matched in both frames."
            message = f"{source}: " + message + f" Usable faces by frame: {reports[0]['usable']} / {reports[1]['usable']}."
            self.last_result = message
            self._last_capture = self.clock()
            self.emit("vision_activity",{"kind":"recognition_test","message":message,"source":source})
            return {"message":message,"source":source,"names":names,"faces":len(faces),"frames":2,"quality":reports,
                    "matches":[[{k:v for k,v in item.items() if k != "person"} for item in frame_matches] for frame_matches in match_reports]}
        finally:
            self._enrolling = False
            self._explicit_task = None
            self.publish()

    def publish(self):
        data = {"occupancy":self.occupancy.state,"sensor_health":self.occupancy.health,
            "distance_mm":self.occupancy.distance,"health":self.health,"model_health":self.faces.health,
            "subjects":self.subjects,"confirmed_persons":[t["person"] for t in self._tracks if t["person"]],"policy":self.camera.config.policy,"privacy":self.camera.config.privacy,
            "gate":self.gate(),"bursts":self._burst_number,"completed_bursts":self._completed_bursts,"pending":self.pending["trigger"] if self.pending else None,
            "ambiguous":sum(t.get("identity")=="ambiguous" and t.get("observed",False) for t in self._tracks),
            "observed":sum(t.get("observed",False) for t in self._tracks),
            "temporarily_lost":sum(not t.get("observed",False) for t in self._tracks),
            "last_result":self.last_result,"last_greeting":self.last_greeting,
            "last_capture_age_s":int(max(0,self.clock()-self._last_capture)) if self._last_capture is not None else None}
        if data != self._last_status:
            self._last_status = data
            self.emit("perception",data)
