"""Single owner of schema versions; migrations never start perception behaviour."""
from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

from .storage import KadencePaths, backup_sqlite, connect_database

SCHEMA_VERSION = 4

LEGACY_V2 = (
    "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, due REAL NOT NULL, timezone TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', kind TEXT NOT NULL DEFAULT 'reminder', extra TEXT NOT NULL DEFAULT '{}', robot TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL, request_key TEXT NOT NULL UNIQUE)",
    'CREATE INDEX reminders_due ON reminders(state,due)',
    'CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, created REAL NOT NULL)',
    'CREATE TABLE project_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id))',
)

LEGACY_V3 = (
    'CREATE TABLE media (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL, mime_type TEXT NOT NULL, source TEXT NOT NULL, captured REAL NOT NULL, width INTEGER, height INTEGER, size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, created REAL NOT NULL)',
    'CREATE INDEX media_captured ON media(captured)',
    "CREATE TABLE observations (id INTEGER PRIMARY KEY AUTOINCREMENT, media_id INTEGER NOT NULL UNIQUE, project_id INTEGER NOT NULL, captured REAL NOT NULL, question TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', qr TEXT NOT NULL DEFAULT '[]', source_device TEXT NOT NULL, created REAL NOT NULL, FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE, FOREIGN KEY(project_id) REFERENCES projects(id))",
    'CREATE INDEX observations_project ON observations(project_id,captured)',
)

V4 = (
    "ALTER TABLE media ADD COLUMN purpose TEXT NOT NULL DEFAULT 'manual_capture' CHECK(length(purpose) BETWEEN 1 AND 80)",
    "ALTER TABLE media ADD COLUMN expires_at REAL",
    "ALTER TABLE media ADD COLUMN pinned INTEGER NOT NULL DEFAULT 1 CHECK(pinned IN (0,1))",
    "ALTER TABLE media ADD COLUMN deleted_at REAL",
    "CREATE INDEX media_expiry ON media(pinned,expires_at) WHERE deleted_at IS NULL",
    """CREATE TABLE persons (
        id TEXT PRIMARY KEY NOT NULL, display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 120),
        greeting_name TEXT NOT NULL DEFAULT '' CHECK(length(greeting_name)<=120),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        greeting_enabled INTEGER NOT NULL DEFAULT 1 CHECK(greeting_enabled IN (0,1)),
        recognition_enabled INTEGER NOT NULL DEFAULT 0 CHECK(recognition_enabled IN (0,1)),
        enrolled_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
        CHECK(recognition_enabled=0 OR enrolled_at IS NOT NULL))""",
    """CREATE TABLE face_profiles (
        id TEXT PRIMARY KEY NOT NULL, person_id TEXT NOT NULL REFERENCES persons(id),
        model_fingerprint TEXT NOT NULL CHECK(length(model_fingerprint) BETWEEN 1 AND 200),
        preprocessing TEXT NOT NULL CHECK(length(preprocessing) BETWEEN 1 AND 500),
        metric TEXT NOT NULL CHECK(metric IN ('cosine','euclidean')),
        encoding TEXT NOT NULL DEFAULT 'float32-le' CHECK(encoding='float32-le'),
        embedding_dimension INTEGER NOT NULL CHECK(embedding_dimension BETWEEN 1 AND 4096),
        embedding BLOB NOT NULL CHECK(typeof(embedding)='blob' AND length(embedding)=embedding_dimension*4),
        quality_score REAL CHECK(quality_score BETWEEN 0 AND 1),
        reference_media_id INTEGER REFERENCES media(id) ON DELETE RESTRICT,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at REAL NOT NULL)""",
    "CREATE INDEX face_profiles_person ON face_profiles(person_id,active)",
    """CREATE TABLE perception_runs (
        id TEXT PRIMARY KEY NOT NULL, started_at REAL NOT NULL, checkpoint_at REAL NOT NULL,
        ended_at REAL, end_reason TEXT,
        config_fingerprint TEXT NOT NULL, model_fingerprint TEXT,
        CHECK((ended_at IS NULL AND end_reason IS NULL) OR (ended_at IS NOT NULL AND end_reason IS NOT NULL)))""",
    """CREATE TABLE presence_sessions (
        id TEXT PRIMARY KEY NOT NULL, run_id TEXT NOT NULL REFERENCES perception_runs(id),
        person_id TEXT REFERENCES persons(id),
        identity_status TEXT NOT NULL DEFAULT 'unresolved' CHECK(identity_status IN ('unresolved','confirmed','ambiguous')),
        started_at REAL NOT NULL, last_visual_seen_at REAL, checkpoint_at REAL NOT NULL,
        identity_confirmed_at REAL, ended_at REAL, end_reason TEXT,
        initial_trigger TEXT NOT NULL CHECK(length(initial_trigger) BETWEEN 1 AND 80),
        CHECK(identity_status<>'confirmed' OR (person_id IS NOT NULL AND identity_confirmed_at IS NOT NULL)),
        CHECK((ended_at IS NULL AND end_reason IS NULL) OR (ended_at IS NOT NULL AND end_reason IS NOT NULL)))""",
    "CREATE INDEX presence_run_open ON presence_sessions(run_id,ended_at)",
    "CREATE UNIQUE INDEX presence_one_person ON presence_sessions(run_id,person_id) WHERE ended_at IS NULL AND person_id IS NOT NULL",
    """CREATE TABLE perception_events (
        id TEXT PRIMARY KEY NOT NULL, event_type TEXT NOT NULL CHECK(length(event_type) BETWEEN 1 AND 80),
        event_version INTEGER NOT NULL DEFAULT 1 CHECK(event_version>0),
        occurred_at REAL NOT NULL, recorded_at REAL NOT NULL,
        correlation_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES perception_runs(id),
        presence_session_id TEXT REFERENCES presence_sessions(id), person_id TEXT REFERENCES persons(id),
        media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
        observation_id INTEGER REFERENCES observations(id) ON DELETE SET NULL,
        camera_source TEXT, frame_id TEXT, trigger_type TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(length(evidence_json)<=8192 AND json_valid(evidence_json) AND json_type(evidence_json)='object'))""",
    "CREATE INDEX perception_events_correlation ON perception_events(correlation_id,occurred_at)",
    "CREATE INDEX perception_events_session ON perception_events(presence_session_id,occurred_at)",
    "CREATE INDEX perception_events_time ON perception_events(recorded_at)",
    """CREATE TABLE perception_actions (
        id TEXT PRIMARY KEY NOT NULL, presence_session_id TEXT NOT NULL REFERENCES presence_sessions(id),
        person_id TEXT REFERENCES persons(id), correlation_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('greeting','unknown_alert')),
        state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','attempting','delivered','failed','uncertain','suppressed')),
        created_at REAL NOT NULL, expires_at REAL NOT NULL, claimed_at REAL, completed_at REAL,
        outcome TEXT NOT NULL DEFAULT '' CHECK(length(outcome)<=500),
        UNIQUE(presence_session_id,kind),
        CHECK(expires_at>=created_at),
        CHECK(kind<>'greeting' OR person_id IS NOT NULL),
        CHECK(state NOT IN ('attempting','delivered','uncertain') OR claimed_at IS NOT NULL),
        CHECK(state NOT IN ('delivered','failed','uncertain','suppressed') OR completed_at IS NOT NULL))""",
    "CREATE INDEX perception_actions_pending ON perception_actions(state,expires_at)",
)

# Validate historical contracts before attempting DDL; never repair by recreation.
REQUIRED = {
    1: {'records': {'id','kind','text','created','done'}},
    2: {
        'reminders': {'id','text','due','timezone','state','kind','extra','robot','created','request_key'},
        'projects': {'id','name','created'},
        'project_entries': {'id','project_id','kind','text','done','created'},
    },
    3: {
        'media': {'id','path','media_type','mime_type','source','captured','width','height','size_bytes','sha256','created'},
        'observations': {'id','media_id','project_id','captured','question','description','qr','source_device','created'},
    },
    4: {
        'media': {'purpose','expires_at','pinned','deleted_at'},
        'persons': {'id','display_name','recognition_enabled','enrolled_at'},
        'face_profiles': {'id','person_id','model_fingerprint','embedding','embedding_dimension'},
        'perception_runs': {'id','started_at','checkpoint_at','ended_at'},
        'presence_sessions': {'id','run_id','person_id','identity_status','ended_at'},
        'perception_events': {'id','event_type','correlation_id','evidence_json'},
        'perception_actions': {'id','presence_session_id','kind','state','expires_at'},
    },
}


def validate_schema(db: sqlite3.Connection, version: int) -> None:
    for level in range(1, version + 1):
        for table, required in REQUIRED[level].items():
            columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
            if not required <= columns:
                raise RuntimeError(f"database schema v{version} is incomplete: {table}")


def check_integrity(db: sqlite3.Connection) -> None:
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RuntimeError('database integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RuntimeError('database foreign key check failed')


def _apply_migration(db: sqlite3.Connection, version: int) -> None:
    if version == 1:
        statements = ("CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)",)
    else:
        statements = {2: LEGACY_V2, 3: LEGACY_V3, 4: V4}[version]
    # executescript implicitly commits in legacy sqlite3 mode: intentionally do
    # not use it. Every DDL statement and user_version belong to this transaction.
    for statement in statements:
        db.execute(statement)
    db.execute(f'PRAGMA user_version={version}')


def ensure_schema(paths: KadencePaths, *, target: int = SCHEMA_VERSION):
    """Upgrade once before service tasks start; return this attempt's backup path.

    ContextStore may request the historical v1 minimum for standalone use. A
    newer supported database is validated and never downgraded. UtilityStore
    requests the latest version; neither store owns any schema DDL.
    """
    if type(target) is not int or not 1 <= target <= SCHEMA_VERSION:
        raise ValueError('unsupported schema target')
    paths.prepare()
    backup = None
    with closing(connect_database(paths.database, timeout=5.0)) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version not in range(SCHEMA_VERSION + 1):
            raise RuntimeError('unsupported context database version')
        if version >= target:
            validate_schema(db, version)
            return None
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('BEGIN IMMEDIATE')
        try:
            # Re-read after acquiring the writer reservation: another startup
            # may have completed the migration while this connection waited.
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in range(SCHEMA_VERSION + 1):
                raise RuntimeError('unsupported context database version')
            validate_schema(db, version)
            if version < target:
                if version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                    raise RuntimeError('unversioned nonempty database; explicit recovery required')
                check_integrity(db)
                if version:
                    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                    backup = paths.backups_dir / f'schema-v{version}-before-v{target}-{stamp}-{uuid.uuid4().hex}.sqlite3'
                    # A separate read connection snapshots the committed source
                    # while BEGIN IMMEDIATE prevents any competing writer.
                    backup_sqlite(paths.database, backup)
                    if version == 1 and not paths.utility_backup.exists():
                        backup_sqlite(backup, paths.utility_backup)
                    if version == 2 and not paths.observation_schema_backup.exists():
                        backup_sqlite(backup, paths.observation_schema_backup)
                for next_version in range(version + 1, target + 1):
                    _apply_migration(db, next_version)
                validate_schema(db, target)
                check_integrity(db)
            db.commit()
        except BaseException:
            db.rollback()
            raise
    if os.name != 'nt':
        paths.database.chmod(0o600)
    return backup
