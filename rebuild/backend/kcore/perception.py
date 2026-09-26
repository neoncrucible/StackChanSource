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
from .local_faces import LocalFaces, quality_message, similarity
from .face_sequence import FaceSequence, LiveEnrollment, recognition_diagnostic
from .face_media import preview, reference
from .perception_store import PerceptionStore


from .occupancy import Occupancy  # compatibility for callers of the existing tracker
from .sensor_sampler import SensorSampler, SensorObservation

TRIGGERS = frozenset({"arrival", "gesture", "close_approach", "heartbeat"})
REASONS = frozenset({"ready", "observation_only", "privacy", "policy_off", "stopped", "lifecycle_check_required",
    "voice_busy", "camera_busy", "enrolling", "zone_clear", "sensor_unknown", "cooldown", "expired", "session_changed",
    "captured", "cancelled", "unavailable", "storage_unavailable", "models_missing", "models_invalid", "low_salience", "timeout"})


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


class LookInterrupted(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason.replace("_", " "))


class CaptureBudget:
    def __init__(self): self.requests, self.last = deque(), -1e9
    def delay(self, now):
        while self.requests and self.requests[0] <= now-60: self.requests.popleft()
        return max(0,self.last+20-now,self.requests[0]+60-now if len(self.requests)+6>18 else 0)
    def reserve(self, now):
        if self.delay(now)>0: return False
        self.requests.extend([now]*6); self.last = now
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
        self._arrival_retry = None
        self._arrival_retried = False
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
        self._arrival_retry = None
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
        self._arrival_retried = False
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
        if self._arrival_retry:
            retry = self._arrival_retry
            if (now > retry['expires'] or retry['generation'] != self.camera.generation or retry['session'] != self.sampler.reflex.session_id
                    or self.occupancy.state != 'OCCUPIED' or any(t['person'] and t.get('observed') for t in self._tracks)):
                self._arrival_retry = None
            elif now >= retry['after'] and not self.busy() and not (self.task and not self.task.done()) and self.budget.delay(now)==0:
                self._arrival_retry = None
                self.request('arrival',defer=False)
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
            self._arrival_retry = None
            self._arrival_retried = False
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
        started = False
        async def run():
            nonlocal started
            started = True
            await self._burst(trigger)
        self.task = asyncio.create_task(run(), name="kadence-perception")
        def retired(task):
            if task.cancelled() and not started: self._decision(trigger,'cancelled','cancelled')
        self.task.add_done_callback(retired)
        return True

    async def _burst(self, trigger):
        if trigger not in TRIGGERS: return
        generation = self.camera.generation
        terminal = False
        self._burst_number += 1
        self.health = "processing"
        self.publish()
        try:
            async with asyncio.timeout(18):
                async with self.camera.unitv2.burst():
                    await self._analyze_burst(trigger)
            self.camera.check(generation)
            self.health = "ready"
            self._completed_bursts += 1
            self._decision(trigger,"completed","captured")
            terminal = True
            # Release the camera before optional speech or notification.
            await self.dispatch(generation)
            # The arrival look can happen while someone is still turning/sitting.
            # One later attempt respects the same budget and occupancy session.
            if (trigger == 'arrival' and self.camera.config.greetings and self.occupancy.state == 'OCCUPIED'
                    and not self._arrival_retried and not any(t['person'] and t.get('observed') for t in self._tracks)
                    and await self.db('profiles')):
                self._arrival_retried = True
                now = self.clock()
                self._arrival_retry = {'after':now+max(3,self.budget.delay(now)), 'expires':now+35,
                    'generation':generation, 'session':self.sampler.reflex.session_id}
                self.last_greeting = 'No identity confirmed yet. One follow-up look is queued while this visit remains occupied.'
        except asyncio.CancelledError:
            self.health = "idle"
            if not terminal: self._decision(trigger,"cancelled","cancelled")
            raise
        except LookInterrupted as exc:
            self.health = "idle"
            self.last_result = "Look interrupted: " + exc.reason.replace('_',' ') + "."
            if not terminal: self._decision(trigger,"cancelled",exc.reason)
        except Exception as exc:
            self.health = self.faces.health if self.faces.health in {"models_missing","models_invalid"} else "unavailable"
            reason = "timeout" if isinstance(exc,TimeoutError) else self.health
            self.last_result = "Camera look failed: " + reason.replace('_',' ') + "."
            self.emit("vision_activity",{"kind":"automatic_look","message":self.last_result})
            if not terminal: self._decision(trigger,"failed",reason)
        finally:
            if self.health == "processing": self.health = "idle"
            self.publish()

    def _recognition_event(self, kind, sequence, report, frame, frames, *, reason=None):
        matches = [t['match'] for t in sequence.current]
        best = max(matches, key=lambda m:m['score'] if m['score'] is not None else -2, default={})
        reason = reason or ('confirmed' if sequence.confirmed else
            'no_face' if not report.get('detected') else 'no_usable_face' if not report.get('usable') else
            best.get('reason') if best.get('reason') != 'candidate' else 'insufficient_evidence')
        data = recognition_diagnostic({**report, **best, 'kind':kind, 'reason':reason,
            'frames':frames,'confirmed':len(sequence.confirmed),'source':frame.source,
            'stable':sum(t['seen']>=2 for t in sequence.current),
            'hits':max((t['hits'] for t in sequence.current),default=0), 'samples':len(sequence.profiles)})
        self.emit('recognition_evidence',data)
        return data

    async def _recognize(self, *, kind, trigger=None, live=False):
        generation = self.camera.generation
        profiles = await self.db("profiles")
        sequence = FaceSequence(profiles)
        reports, match_reports, source = [], [], None
        names_seen = set()
        # Automatic work gets up to six frames. Explicit live testing keeps going
        # after a match, so the owner can actually try movement and different views.
        limit = 20 if live else 6
        for index in range(limit):
            if index: await asyncio.sleep(.5)
            self.camera.check(generation)
            if self.busy(): raise LookInterrupted("voice_busy")
            if kind == 'automatic':
                if self.gate() != 'ready': raise LookInterrupted('cancelled')
                if trigger != 'gesture' and self.occupancy.state == 'CLEAR': raise LookInterrupted('zone_clear')
            frame = await self.camera.acquire(purpose='automatic' if kind=='automatic' else 'manual', source=source, timeout=8)
            if source is not None and frame.source != source:
                raise RuntimeError('Camera source changed during recognition. Choose a specific camera and retry.')
            source = frame.source
            faces, report = await self._face_evidence(frame,show=kind=='test')
            self.camera.check(generation)
            tracks = sequence.update(faces)
            reports.append(report)
            match_reports.append([{k:v for k,v in t['match'].items() if k != 'person'} for t in tracks])
            names_seen.update(sequence.confirmed)
            evidence = self._recognition_event(kind,sequence,report,frame,index+1)
            self._last_capture = self.clock()
            if kind == 'test':
                text = f"Live check {index+1}/{limit}: {report['usable']} usable face(s); {len(sequence.confirmed)} confirmed now."
                if evidence.get('score') is not None: text += f" Similarity {evidence['score']:.3f}; required 0.55."
                self.emit('vision_activity',{'kind':'recognition_test','message':text,'source':source})
            if not live and index >= 1:
                if faces and len(sequence.confirmed)==len(faces): break
                if not profiles and tracks and all(t['seen']>=2 for t in tracks): break
        return sequence,frame,reports,match_reports,names_seen

    async def _analyze_burst(self, trigger):
        generation = self.camera.generation
        sequence,frame,reports,_,_ = await self._recognize(kind='automatic',trigger=trigger)
        present = []
        for track in sequence.current:
            if track['seen'] < 2: continue
            face, confirmed, identity = track['face'],track['person'],track['identity']
            # A single candidate is not evidence that this is an unknown person.
            if not confirmed and track['match']['person']: identity = 'ambiguous'
            existing = next((t for t in self._tracks if confirmed and t['person']==confirmed),None)
            if not confirmed:
                used_sessions = {t['session'] for t in present}
                possible = sorted(((similarity(t['embedding'],face.embedding),t) for t in self._tracks
                    if t['person'] is None and self.clock()-t['seen'] < 10 and t['session'] not in used_sessions), key=lambda item:item[0], reverse=True)
                existing = possible[0][1] if possible and possible[0][0]>=.7 and (len(possible)==1 or possible[0][0]-possible[1][0]>=.08) else None
            action = 'greeting' if confirmed and self.camera.config.greetings and confirmed not in self._visit_greeted else 'unknown_alert' if not confirmed and identity=='unresolved' and self.camera.config.unknown_alerts and not self._unknown_notified else None
            session = await self.db('observe',run=self.run,person=confirmed,frame=frame,trigger=trigger,
                session=existing['session'] if existing else None,identity=identity,action=action)
            self.camera.check(generation)
            present.append({'session':session,'person':confirmed,'identity':identity,'embedding':face.embedding,'seen':self.clock(),'observed':True})
        sessions = {t['session'] for t in present}
        self._tracks = present + [{**t,'observed':False} for t in self._tracks if t['session'] not in sessions and self.clock()-t['seen']<180]
        self.subjects = len(present)
        names = {p['id']:p['display_name'] for p in await self.db('persons')}
        self.camera.check(generation)
        confirmed_names = [names[t['person']] for t in present if t['person'] in names]
        self.last_result = ('Recognised: '+', '.join(confirmed_names)+'.') if confirmed_names else (
            quality_message(reports[-1]) if not sequence.current else f"{len(sequence.current)} usable face(s); no enrolled identity confirmed across {len(reports)} fresh frames.")
        self.emit('vision_activity',{'kind':'automatic_look','message':self.last_result,'source':frame.source})
        await self.db('event',run=self.run,kind='capture_result',trigger=trigger,frame=frame,
            evidence={'frames':len(reports),'subjects':self.subjects,'confirmed':len(confirmed_names)})
        self._last_failure = None
        return True

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
        if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name): raise ValueError('Enter a name of 1–80 characters.')
        await self.interrupt()
        self._explicit_task = asyncio.current_task()
        self._enrolling = True
        generation = self.camera.generation
        training = LiveEnrollment()
        references = []
        source = None
        try:
            # Validate profile/name before asking the owner to spend time training.
            people = await self.db('persons')
            if person and not any(p['id']==person for p in people): raise ValueError('That profile is no longer saved.')
            if any(p['id']!=person and p['display_name'].casefold()==name.strip().casefold() for p in people):
                raise ValueError('That name is already saved. Select its profile and use REPLACE SAMPLES.')
            async with asyncio.timeout(120):
                async with self.camera.unitv2.burst():
                    for attempt in range(180):
                        self.camera.check(generation)
                        if self.busy(): raise LookInterrupted('voice_busy')
                        self.emit('enrollment',{'state':'capturing','sample':len(training.faces),'total':training.TOTAL,'message':training.prompt,'view':training.VIEWS[training.stage]})
                        if attempt: await asyncio.sleep(.5)
                        frame = await self.camera.acquire(purpose='enrollment',source=source,timeout=8)
                        if source is not None and source != frame.source: raise RuntimeError('Camera source changed during training. Choose a specific camera and retry.')
                        source = frame.source
                        faces,report = await self._face_evidence(frame,show=True)
                        self.camera.check(generation)
                        accepted,message = training.offer(faces,report)
                        count = len(training.faces)
                        if accepted:
                            # Keep one front and each side view, only with explicit opt-in.
                            references.append(await settled_thread(reference,frame,faces[0]) if keep_photos and count in (1,5,9) else None)
                        self.emit('enrollment',{'state':'accepted' if accepted else 'waiting','sample':count,'total':training.TOTAL,'message':message,'source':source,'view':training.VIEWS[training.stage]})
                        self.emit('recognition_evidence',recognition_diagnostic({**report,'kind':'enrollment','reason':'capturing','accepted':count,'total':training.TOTAL,'view':training.VIEWS[training.stage],'source':source}))
                        if training.done: break
                    if not training.done: raise TimeoutError()
            # No partial profile is ever published. Stop must succeed before commit.
            self.camera.check(generation)
            saved = await self.db('enroll',name=name,vectors=[f.embedding for f in training.faces],person=person,
                references=references if keep_photos else None)
            photo_message = '3 local review photos saved; select the profile to view them.' if keep_photos else 'No photographs saved.'
            message = f'Saved: {name}. {training.TOTAL} face samples covering front, both sides, chin tilt and distance. {photo_message} Run LIVE RECOGNITION CHECK while moving normally.'
            self.emit('enrollment',{'state':'saved','sample':training.TOTAL,'total':training.TOTAL,'message':message})
            self.emit('recognition_evidence',{'kind':'enrollment','reason':'saved','accepted':training.TOTAL,'total':training.TOTAL})
            return {'message':message,'person_id':saved,'persons':await self.db('persons'),'samples':training.TOTAL}
        except BaseException as exc:
            message = ('Training timed out before all five views were captured. Previous samples were kept. Retry and follow the live guidance.' if isinstance(exc,TimeoutError) else
                'Training interrupted. Refresh Profiles to check the saved state.' if isinstance(exc,asyncio.CancelledError) else
                'Training paused for voice. Previous samples were kept; restart training when the reply finishes.' if isinstance(exc,LookInterrupted) else
                str(exc) if type(exc) in {RuntimeError,ValueError} else 'Training failed. Check the camera and local face models.')
            self.emit('enrollment',{'state':'failed','message':message})
            if isinstance(exc,TimeoutError): raise RuntimeError(message) from None
            raise
        finally:
            training.faces.clear(); references.clear()
            self._enrolling = False
            self._explicit_task = None
            self.publish()

    async def test_recognition(self, *, live=False):
        """Explicit local check; never manufactures an automatic visit or greeting."""
        await self.interrupt()
        self.camera.check()
        self._explicit_task = asyncio.current_task()
        self._enrolling = True
        generation = self.camera.generation
        try:
            async with asyncio.timeout(30 if live else 18):
                async with self.camera.unitv2.burst():
                    sequence,frame,reports,matches,seen = await self._recognize(kind='test',live=live)
            self.camera.check(generation)
            people = {p['id']:p['display_name'] for p in await self.db('persons')}
            self.camera.check(generation)
            names = [people[p] for p in sorted(sequence.confirmed) if p in people]
            seen_names = [people[p] for p in sorted(seen) if p in people]
            message = 'Recognised now: '+', '.join(names)+'.' if names else 'No enrolled identity confirmed in the latest frame.'
            if live and seen_names: message += ' Confirmed during this live check: '+', '.join(seen_names)+'.'
            if not sequence.current: message += ' '+quality_message(reports[-1])
            elif not sequence.profiles: message = 'A face was seen, but there are no enabled compatible profiles. Enrol a profile first.'
            elif not names:
                best = max(matches[-1],key=lambda m:m['score'] if m['score'] is not None else -2)
                if best['reason']=='below_threshold': message += f" Best similarity {best['score']:.3f}; required {best['threshold']:.2f}. Use live training to cover this camera and viewing angle."
                elif best['reason'] in {'ambiguous','duplicate_identity'}: message += ' Competing face/profile evidence; no identity assigned.'
                else: message += ' More agreeing evidence is needed; no greeting was attempted.'
            message = frame.source+': '+message+' Usable faces by frame: '+' / '.join(str(r['usable']) for r in reports)+'.'
            self.last_result = message
            self.emit('vision_activity',{'kind':'recognition_test','message':message,'source':frame.source})
            return {'message':message,'source':frame.source,'names':names,'seen_names':seen_names,'faces':len(sequence.current),'frames':len(reports),'quality':reports,'matches':matches}
        except TimeoutError:
            raise RuntimeError('Live check timed out. The camera has been released; inspect Activity and retry.') from None
        finally:
            self._enrolling = False
            self._explicit_task = None
            self.publish()

    def publish(self):
        data = {"occupancy":self.occupancy.state,"sensor_health":self.occupancy.health,
            "distance_mm":self.occupancy.distance,"health":self.health,"model_health":self.faces.health,
            "subjects":self.subjects,"confirmed_persons":[t["person"] for t in self._tracks if t["person"]],"policy":self.camera.config.policy,"privacy":self.camera.config.privacy,
            "gate":self.gate(),"bursts":self._burst_number,"completed_bursts":self._completed_bursts,"pending":self.pending["trigger"] if self.pending else 'arrival' if self._arrival_retry else None,
            "ambiguous":sum(t.get("identity")=="ambiguous" and t.get("observed",False) for t in self._tracks),
            "observed":sum(t.get("observed",False) for t in self._tracks),
            "temporarily_lost":sum(not t.get("observed",False) for t in self._tracks),
            "last_result":self.last_result,"last_greeting":self.last_greeting,
            "last_capture_age_s":int(max(0,self.clock()-self._last_capture)) if self._last_capture is not None else None}
        if data != self._last_status:
            self._last_status = data
            self.emit("perception",data)
