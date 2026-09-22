# Perception v4 foundation — 2026-09-21

Approved architecture from the repository review. Work branch:
`kadence/functionality`. Accepted hardware integration baseline:
`kadence/sensor-clean-base` at `7aa7c2a`.

## This milestone

Host 0.3.7 centralizes schema management and adds schema v4. Firmware remains
0.21.6; no flash is required. Normal application startup upgrades existing
supported databases before utility tasks start. The explicit operator tool below
lets the owner inspect and upgrade while the desktop is closed.

No autonomous capture, face enrollment, recognition, presence tracking, greeting,
alert delivery, or retention sweep is enabled by this milestone. The six new
tables start empty. Existing manual capture, description, save, reminders and
voice retain their existing behaviour. Media registration independent of project
observations is a later runtime implementation step, not added here.

## Architecture decisions

- Keep zone occupancy, individual identity evidence, and camera operating state
  separate. A ToF target is not necessarily a person. Invalid/stale samples are
  unknown evidence, not absence. Deduplicate cached sequence numbers.
- Occupancy transitions: UNKNOWN, CLEAR, ARRIVAL_CANDIDATE, OCCUPIED,
  DEPARTURE_CANDIDATE. Track sensor health separately. Apply monotonic debounce,
  hysteresis, minimum event intervals and capture budgets in runtime config.
- Per-subject presence: observed, temporarily lost, ended. Identity: unresolved,
  confirmed, ambiguous. ToF cannot renew an individual's last visual evidence.
- OFF disables autonomous vision; EVENT_ONLY permits bounded meaningful events;
  AWARE additionally permits occasional checks. Manual camera access is separate.
  Privacy overrides all camera consumers. Defer ACTIVE and dedicated mode enums.
- A single PerceptionController owns runtime state and candidate accumulation.
  The sensor sampler uses the existing serial owner, never a second COM4 client.
- CameraManager will own source selection, privacy, total deadlines, priorities,
  bounded/coalesced requests, cancellation generations and failure backoff.
  Preserve the existing in-turn onboard capture callback to avoid voice deadlock.
  AUTO prefers UnitV2; permitted available onboard capture is the fallback.
- Immutable acquisition results are separate from DeskVision's mutable UI preview.
  Always record actual source, frame/request identity, dimensions and timing.
- Local recognition is separate from Gemini object description. Explicit enrollment
  only; no automatic promotion of uncertain matches into face profiles. Embedding
  finite-value validation, normalization and model compatibility belong in the
  future typed profile service in addition to database shape constraints.
- Face counts do not prove identity continuity. Identity evidence expires even
  when occupancy/count remain unchanged. Sparse unknown tracking can be ambiguous.
- Store meaningful decisions, not every sensor sample, frame or successful heartbeat.
  Use correlation UUIDs; no incident table, vector database or global UNKNOWN person.
- Session UUID is the temporary subject token. Resolve its person association with
  an explicit history event. Multiple subjects may coexist. Do not use the existing
  robot lifecycle enum `Presence` for human occupancy.
- Atomic action creation/claiming belongs in the future perception store; the
  dispatcher performs I/O outside the transaction. UNIQUE(session,kind) prevents
  duplicate greetings/unknown alerts. Prefer at-most-once attempts; interrupted
  ambiguous audio becomes uncertain and is not replayed. Recheck eligibility and
  expiry before dispatch. Recognition is not authorization.
- On restart/resume, reconcile old runs/sessions at last durable evidence, not at
  restart time as if continuous presence were known. This logic is not active yet.

## Storage contracts

One canonical database: `<data-root>/database/kadence.sqlite3`.
Default Windows root is `%LOCALAPPDATA%/Kadence`, overridden by KADENCE_DATA_DIR.
It is not the source checkout. Existing image files remain under
`media/images/YYYY/MM/`. Existing table IDs, contents and schema contracts remain.

New tables:

| Table | Contract |
| --- | --- |
| persons | Stable application UUID, editable names, explicit enrollment and recognition enablement |
| face_profiles | Person FK, bounded float32-le BLOB/dimension, model and preprocessing identity, optional reference-media FK |
| perception_runs | Process/run UUID, configuration/model identity, durable checkpoint and end reason |
| presence_sessions | Run FK, nullable person, identity state/evidence times, end reason; one open session per known person per run |
| perception_events | Typed/versioned append-oriented history; correlation UUID, optional evidence/media links, bounded object JSON |
| perception_actions | Greeting/unknown-alert intent and outcome, session/kind uniqueness, expiry and attempt timestamps |

Existing media gains `purpose`, `expires_at`, `pinned`, `deleted_at`. Existing
and manually saved images default to pinned/manual_capture and never expire.
Future autonomous retention must explicitly choose purpose and lifetime. Active
profile references must protect media; reference-media deletion is restricted.
Use tombstones for file expiry so project observation history remains intact.
The existing observations table remains a project annotation, not an automatic
per-frame inference sink. No automatic rows or images are added at this stage.

Future stores must validate event types, UUIDs, finite timestamps/embeddings,
semantic state transitions, same-run session/event links, and profile eligibility.
Database constraints provide relational/shape protection, not the whole policy.

## Migration and recovery

`schema.ensure_schema` is the sole DDL/version owner. ContextStore requests a v1
minimum for standalone compatibility; UtilityStore requests latest (v4). A newer
supported schema is never downgraded. Connections explicitly enable and verify FKs.

Before upgrading an existing database, a uniquely named SQLite backup is produced
under `backups/schema-vN-before-v4-<UTC>-<UUID>.sqlite3`. A writer reservation keeps
other writers out while the read connection snapshots committed pages including WAL.
Source and migrated DB undergo integrity and FK checks. Explicit transaction wraps
all schema changes and user_version. Failed DDL rolls back; failed backup prevents
DDL. Backups survive failed attempts and are never overwritten by later retries.

If both `context.sqlite3` and the canonical database exist, startup refuses to
choose between them. Both are preserved for reconciliation. A stale layout backup
is never trusted as the source of a new canonical database.

Close desktop/tray and any headless Kadence host before using the operator tool.
From Windows PowerShell after switching to this branch:

```powershell
Set-Location 'C:\KadenceX\source\rebuild'
uv run --no-project --python 3.12 .\tools\storage_status.py
uv run --no-project --python 3.12 .\tools\storage_status.py --upgrade
```

Default invocation is read-only and prints only schema/integrity and row counts,
not record text. `--data-dir` accepts an explicit existing data root. `--upgrade`
refuses an empty/wrong directory and an existing desktop lock. Normal startup can
still initialize a new installation. Successful upgrade prints its rollback path.

Expected: KADENCE_STORAGE PASS schema=4 integrity=ok foreign_keys=ok. Old table
counts remain equal; the six perception tables have zero rows. Re-running is a
no-op. Then start the source desktop normally and check existing reminders and a
saved observation. The owner confirmed migration, reopen, reminders and normal voice on 2026-09-22.

Rollback is a data restore, not merely a Git switch: close all Kadence processes;
archive the current v4 DB together with any -wal/-shm sidecars; restore the exact
pre-upgrade snapshot to database/kadence.sqlite3 with no mismatched sidecars; keep
media unchanged; then run the accepted baseline. Changes made after the snapshot
are not present in that restored database. Never overwrite the only copy of v4.
Do not attempt a reverse migration by editing PRAGMA user_version.

## UnitV2 lifecycle gate

The uploaded factory JS `core/canvas.draw.js` stopLoadStream only clears browser
intervals. `core/post.server.js` contains function selection and stoptrain; neither
establishes a camera producer stop/standby API. Current `unitv2_network.py` starts
Camera Stream and closes retrieval after one frame. Producer-off, sensor standby,
thermal improvement and physical privacy remain unverified. No guessed endpoint
or process termination has been added.

Next read-only hardware evidence, in PowerShell (same home LAN):

```powershell
ssh m5stack@192.168.40.175 'ls -l /home/m5stack /opt; ps | grep -E "[p]ython|[c]amera|[u]nitv2"'
```

This identifies installed service locations/processes. Inspect those service
handlers before choosing any reversible stop/start experiment. Keep working USB
SSH/recovery access and the prior configuration archive. Measure startup latency
and producer activity/power before and after any verified lifecycle operation.
Do not claim HTTP disconnection is camera shutdown. Unsupported standby must stay
visible in the eventual camera adapter's capabilities.

## Subsequent milestones

1. Investigate camera lifecycle (owner's v4 migration and reopen confirmed).
2. CameraManager, immutable frame results, source arbitration and privacy/cancel tests.
3. In-memory occupancy in observation-only mode; sensor stale/reset/sleep tests.
4. Local enrollment, recognition and multi-subject session evidence.
5. Event/heartbeat budgets, transactional action store, dispatcher, retention quota.
6. Physical tests for long occupied desk, person replacement, extra person,
   unavailable camera, mid-capture privacy and restart before enabling autonomy.

## Validation for this milestone

61 focused tests passed, 1 Windows-only desktop test skipped, 28 subtests passed.
Coverage includes historical v1/v2/v3 upgrades, fresh initialization, already-v4
reopen, failed backup, interrupted DDL rollback/retry, committed WAL backup,
concurrent migration, invalid FKs, future/incomplete schemas, legacy/canonical
ambiguity, reminder states, saved media, operator read-only/upgrade checks, and
existing desktop/voice/camera tests. Tests use temporary databases; the owner's
Windows database has not been touched by this development session.

## Windows confirmation and post-answer alignment (2026-09-22)

Owner's storage upgrade passed with schema=4, integrity=ok and foreign_keys=ok.
The pre-upgrade rollback snapshot was created; four reminders remained and the
new perception tables were empty. The owner subsequently confirmed the reopen
and normal operation check passed.

Host 0.3.8 removes the unconditional post-answer body.pose(yaw=0, pitch=430).
That command moved to a fixed target and released torque there; it did not
return to the previous pose. Completing speech now sends no servo repositioning,
preserving the operator's camera alignment. No guessed home angle, calibration
change or firmware change is introduced. Explicit movement remains available.
The existing repeated-turn and reconnect tests now require zero pose commands
and preservation of a nonzero initial pose. Physical confirmation of the fix
requires two normal questions after restarting the updated host; no flash is needed.
