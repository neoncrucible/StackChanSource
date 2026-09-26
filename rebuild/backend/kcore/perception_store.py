"""Typed perception persistence. Short transactions; delivery always outside SQLite."""
from __future__ import annotations
from contextlib import closing, nullcontext
import json
import math
import sqlite3
import time
import threading
import uuid
from .local_faces import FINGERPRINT, PREPROCESSING, encode, decode
from .storage import connect_database
from .face_media import ProfilePhotos

_media_lock = threading.RLock()


def ident(): return str(uuid.uuid4())
def check_id(value):
    if str(uuid.UUID(value)) != value: raise ValueError("Invalid perception identifier.")
    return value


class PerceptionStore:
    def __init__(self, database):
        self.database = database
        self.photos = ProfilePhotos(database)

    def call(self, operation, **args):
        allowed = {"begin", "end", "enroll", "persons", "photos", "profiles", "update_person", "activity", "forget", "observe", "expire", "event", "claim", "complete"}
        if operation not in allowed: raise ValueError("Unknown perception operation.")
        media_operation = operation in {"enroll","forget","photos","persons"}
        with _media_lock if media_operation else nullcontext(), closing(connect_database(self.database, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            staged = []
            try:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    if operation == "enroll": args["staged"] = staged
                    result = getattr(self, "_"+operation)(db, **args)
            except BaseException:
                for path in staged:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass  # Bounded orphan cleanup retries on next profile access.
                raise
            if media_operation:
                with db: cleaned = self.photos.cleanup(db)
                if operation == "forget" and not cleaned:
                    raise RuntimeError("Profile removed; a local review photo could not be deleted. Close programs using it and refresh Profiles to retry.")
            return result

    def _begin(self, db, fingerprint):
        now = time.time()
        # A crashed attempt is deliberately never replayed.
        db.execute("UPDATE perception_actions SET state='uncertain',completed_at=?,outcome='interrupted' WHERE state='attempting'", (now,))
        db.execute("UPDATE perception_actions SET state='suppressed',completed_at=?,outcome='restart' WHERE state='pending'", (now,))
        db.execute("UPDATE presence_sessions SET ended_at=coalesce(last_visual_seen_at,checkpoint_at),end_reason='restart' WHERE ended_at IS NULL")
        db.execute("UPDATE perception_runs SET ended_at=checkpoint_at,end_reason='restart' WHERE ended_at IS NULL")
        run = ident()
        db.execute("INSERT INTO perception_runs(id,started_at,checkpoint_at,config_fingerprint,model_fingerprint) VALUES(?,?,?,?,?)", (run,now,now,fingerprint,FINGERPRINT))
        return run

    def _end(self, db, run, reason="stopped"):
        check_id(run)
        self._expire(db, run=run, cutoff=float("inf"), reason=reason)
        db.execute("UPDATE perception_runs SET ended_at=checkpoint_at,end_reason=? WHERE id=? AND ended_at IS NULL", (reason,run))

    def _persons(self, db):
        rows = db.execute("""SELECT p.id,p.display_name,p.recognition_enabled,p.greeting_enabled,
            p.enrolled_at,p.updated_at,count(f.id) AS samples,
            count(f.reference_media_id) AS photo_count,
            coalesce(sum(f.model_fingerprint=? AND f.preprocessing=? AND f.metric='cosine'
            AND f.encoding='float32-le' AND f.embedding_dimension=128),0) AS compatible_samples
            FROM persons p LEFT JOIN face_profiles f ON f.person_id=p.id AND f.active=1
            WHERE p.active=1 GROUP BY p.id ORDER BY p.display_name LIMIT 32""", (FINGERPRINT,PREPROCESSING))
        return [dict(r) for r in rows]

    def _photos(self, db, person):
        check_id(person)
        return self.photos.read(db,person)

    def _update_person(self, db, person, name, recognition_enabled, greeting_enabled):
        check_id(person)
        self._check_name(db,name,person)
        if type(recognition_enabled) is not bool or type(greeting_enabled) is not bool:
            raise ValueError("Invalid profile switches.")
        if not db.execute("SELECT 1 FROM persons WHERE id=? AND active=1",(person,)).fetchone():
            raise ValueError("That profile is no longer saved.")
        db.execute("UPDATE persons SET display_name=?,greeting_name=?,recognition_enabled=?,greeting_enabled=?,updated_at=? WHERE id=?",
                   (name.strip(),name.strip(),recognition_enabled,greeting_enabled,time.time(),person))
        db.execute("UPDATE perception_actions SET state='suppressed',outcome='profile_changed',completed_at=? WHERE person_id=? AND state='pending'",(time.time(),person))

    def _activity(self, db):
        # Fixed metadata only: no images, embeddings or free-form saved text.
        events = [dict(r) for r in db.execute("""SELECT occurred_at AS time,event_type AS kind,trigger_type AS trigger,
            camera_source AS source,evidence_json FROM perception_events ORDER BY occurred_at DESC LIMIT 60""")]
        for event in events:
            evidence=json.loads(event.pop("evidence_json"))
            event["detail"]={k:evidence[k] for k in ("decision","reason","frames","subjects","confirmed","health","state","identity") if k in evidence}
        actions = [dict(r) for r in db.execute("""SELECT created_at AS time,kind,state,outcome FROM perception_actions
            ORDER BY created_at DESC LIMIT 30""")]
        return sorted(events+actions,key=lambda item:item["time"],reverse=True)[:80]

    @staticmethod
    def _check_name(db, name, person=None):
        if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80 or any(ord(c)<32 for c in name):
            raise ValueError("Enter a name of 1–80 characters.")
        if db.execute("SELECT 1 FROM persons WHERE active=1 AND lower(display_name)=lower(?) AND id!=?",(name.strip(),person or "")).fetchone():
            raise ValueError("That name is already saved. Select its profile and use REPLACE SAMPLES.")

    def _profiles(self, db):
        result = []
        rows = db.execute("""SELECT f.person_id,f.embedding FROM face_profiles f JOIN persons p ON p.id=f.person_id
            WHERE f.active=1 AND p.active=1 AND p.recognition_enabled=1 AND f.model_fingerprint=?
            AND f.preprocessing=? AND f.metric='cosine' AND f.encoding='float32-le' AND f.embedding_dimension=128
            ORDER BY f.person_id,f.created_at,f.id LIMIT 768""", (FINGERPRINT,PREPROCESSING))
        for row in rows:
            try: result.append((row[0],decode(row[1])))
            except ValueError: continue
        return result

    def _enroll(self, db, name, vectors, person=None, references=None, staged=None):
        self._check_name(db,name,person)
        if not 3 <= len(vectors) <= 24: raise ValueError("Enrollment requires 3–24 face samples.")
        blobs = [encode(v) for v in vectors]
        media = self.photos.add(db,references,staged,count=len(blobs))
        now = time.time()
        if person:
            check_id(person)
            if not db.execute("SELECT 1 FROM persons WHERE id=? AND active=1",(person,)).fetchone(): raise ValueError("That profile is no longer saved.")
            # Old samples remain intact until all new samples validate in this transaction.
            self.photos.retire(db,person)
            db.execute("DELETE FROM face_profiles WHERE person_id=?",(person,))
            db.execute("UPDATE persons SET enrolled_at=?,updated_at=? WHERE id=?",(now,now,person))
        else:
            if db.execute("SELECT count(*) FROM persons WHERE active=1").fetchone()[0] >= 32: raise ValueError("Remove an unused profile before enrolling another person.")
            person = ident()
            db.execute("INSERT INTO persons(id,display_name,greeting_name,recognition_enabled,enrolled_at,created_at,updated_at) VALUES(?,?,?,1,?,?,?)", (person,name.strip(),name.strip(),now,now,now))
        for blob,photo in zip(blobs,media,strict=True):
            db.execute("""INSERT INTO face_profiles(id,person_id,model_fingerprint,preprocessing,metric,embedding_dimension,embedding,created_at,reference_media_id)
                VALUES(?,?,?,?,'cosine',128,?,?,?)""", (ident(),person,FINGERPRINT,PREPROCESSING,blob,now,photo))
        return person

    def _forget(self, db, person):
        check_id(person)
        now = time.time()
        # Remove biometric data and names; retain anonymous relational history.
        self.photos.retire(db,person)
        db.execute("DELETE FROM face_profiles WHERE person_id=?", (person,))
        db.execute("UPDATE persons SET active=0,recognition_enabled=0,greeting_enabled=0,display_name='Removed profile',greeting_name='',updated_at=? WHERE id=?", (now,person))
        db.execute("UPDATE presence_sessions SET ended_at=coalesce(last_visual_seen_at,checkpoint_at),end_reason='profile_removed' WHERE person_id=? AND ended_at IS NULL", (person,))
        db.execute("UPDATE perception_actions SET state='suppressed',completed_at=?,outcome='profile_removed' WHERE person_id=? AND state='pending'", (now,person))

    def _event(self, db, run, kind, trigger, *, session=None, person=None, frame=None, evidence=None):
        check_id(run)
        if session:
            check_id(session)
            if not db.execute("SELECT 1 FROM presence_sessions WHERE id=? AND run_id=?", (session,run)).fetchone(): raise ValueError("Session belongs to another run.")
        if kind not in {"occupancy", "subject_seen", "identity_confirmed", "subject_ended", "capture_failed", "recognition_unavailable", "reflex_proposed", "perception_decision", "capture_result"}: raise ValueError("Unsupported perception event.")
        data = json.dumps(evidence or {}, allow_nan=False, separators=(",",":"))
        if len(data) > 8192: raise ValueError("Perception evidence exceeds limit.")
        now = time.time()
        db.execute("""INSERT INTO perception_events(id,event_type,occurred_at,recorded_at,correlation_id,run_id,presence_session_id,person_id,camera_source,frame_id,trigger_type,evidence_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (ident(),kind,now,now,frame.request_id if frame else ident(),run,session,person,frame.source if frame else None,frame.frame_id if frame else None,trigger,data))
        db.execute("UPDATE perception_runs SET checkpoint_at=? WHERE id=? AND ended_at IS NULL", (now,run))

    def _observe(self, db, run, person, frame, trigger, session=None, identity="unresolved", action=None):
        check_id(run)
        if not db.execute("SELECT 1 FROM perception_runs WHERE id=? AND ended_at IS NULL", (run,)).fetchone(): raise ValueError("Perception run is closed.")
        if not math.isfinite(frame.captured_at): raise ValueError("Invalid capture time.")
        now = frame.captured_at
        if person:
            check_id(person)
            if not db.execute("SELECT 1 FROM persons WHERE id=? AND active=1 AND recognition_enabled=1", (person,)).fetchone(): raise ValueError("Face profile is no longer eligible.")
            identity = "confirmed"
            row = db.execute("SELECT id FROM presence_sessions WHERE run_id=? AND person_id=? AND ended_at IS NULL", (run,person)).fetchone()
            if row: session = row[0]
        row = None
        if session:
            check_id(session)
            row = db.execute("SELECT * FROM presence_sessions WHERE id=? AND run_id=? AND ended_at IS NULL", (session,run)).fetchone()
            if row is None: session = None
        if identity not in {"unresolved", "confirmed", "ambiguous"}: raise ValueError("Invalid identity evidence.")
        if not person and identity == "confirmed": raise ValueError("Confirmation requires an enrolled person.")
        created = session is None
        if created:
            session = ident()
            db.execute("""INSERT INTO presence_sessions(id,run_id,person_id,identity_status,started_at,last_visual_seen_at,checkpoint_at,identity_confirmed_at,initial_trigger)
                VALUES(?,?,?,?,?,?,?,?,?)""", (session,run,person,identity,now,now,now,now if person else None,trigger))
        else:
            # Callers must re-match each visual frame; never extend identity with ToF alone.
            db.execute("UPDATE presence_sessions SET person_id=?,identity_status=?,last_visual_seen_at=?,checkpoint_at=?,identity_confirmed_at=? WHERE id=?", (person,identity,now,now,now if person else None,session))
        if created or (person and row and row["person_id"] != person):
            self._event(db,run,"identity_confirmed" if person else "subject_seen",trigger,session=session,person=person,frame=frame,evidence={"identity":identity})
        else:
            db.execute("UPDATE perception_runs SET checkpoint_at=? WHERE id=?", (now,run))
        if action:
            if action not in {"greeting","unknown_alert"} or (action == "greeting" and not person): raise ValueError("Invalid presence action.")
            db.execute("""INSERT OR IGNORE INTO perception_actions(id,presence_session_id,person_id,correlation_id,kind,created_at,expires_at)
                VALUES(?,?,?,?,?,?,?)""", (ident(),session,person,frame.request_id,action,now,now+20))
        return session

    def _expire(self, db, run, cutoff, reason="visual_evidence_expired"):
        rows = db.execute("SELECT id,person_id FROM presence_sessions WHERE run_id=? AND ended_at IS NULL AND coalesce(last_visual_seen_at,checkpoint_at)<?", (run,cutoff)).fetchall()
        for row in rows:
            db.execute("UPDATE presence_sessions SET ended_at=coalesce(last_visual_seen_at,checkpoint_at),end_reason=? WHERE id=?", (reason,row[0]))
            self._event(db,run,"subject_ended",reason,session=row[0],person=row[1])
        db.execute("""UPDATE perception_actions SET state='suppressed',completed_at=?,outcome='session_ended' WHERE state='pending'
            AND presence_session_id IN (SELECT id FROM presence_sessions WHERE run_id=? AND ended_at IS NOT NULL)""", (time.time(),run))

    def _claim(self, db, run, greetings, unknown_alerts):
        now = time.time()
        rows = db.execute("""SELECT a.*,s.last_visual_seen_at,s.ended_at,p.active,p.recognition_enabled,p.greeting_enabled,p.greeting_name
            FROM perception_actions a JOIN presence_sessions s ON s.id=a.presence_session_id LEFT JOIN persons p ON p.id=a.person_id
            WHERE s.run_id=? AND a.state='pending' ORDER BY a.created_at LIMIT 16""", (run,)).fetchall()
        for row in rows:
            eligible = (row["ended_at"] is None and row["expires_at"] >= now and row["last_visual_seen_at"] >= now-20 and
                ((row["kind"]=="greeting" and greetings and row["active"] and row["recognition_enabled"] and row["greeting_enabled"]) or
                 (row["kind"]=="unknown_alert" and unknown_alerts)))
            # Bound notices across sessions and restarts, not just within one session.
            recent = db.execute("""SELECT 1 FROM perception_actions WHERE state IN ('attempting','delivered','uncertain')
                AND claimed_at>? AND (kind='unknown_alert' AND ?='unknown_alert' OR person_id=?) LIMIT 1""",
                (now-300,row["kind"],row["person_id"])).fetchone()
            if recent: eligible = False
            if not eligible:
                db.execute("UPDATE perception_actions SET state='suppressed',completed_at=?,outcome='ineligible' WHERE id=?", (now,row["id"]))
                continue
            db.execute("UPDATE perception_actions SET state='attempting',claimed_at=? WHERE id=? AND state='pending'", (now,row["id"]))
            return dict(row)
        return None

    def _complete(self, db, action, state):
        check_id(action)
        if state not in {"delivered","failed","uncertain","suppressed"}: raise ValueError("Invalid delivery outcome.")
        db.execute("UPDATE perception_actions SET state=?,completed_at=?,outcome=? WHERE id=? AND state='attempting'", (state,time.time(),state,action))
