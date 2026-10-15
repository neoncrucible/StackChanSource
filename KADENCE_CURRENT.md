# PROJECT KADENCE — canonical state and Astra handover
**Audit date:** 2026-10-12 (Europe/London)
**Latest engineering continuation:** 2026-10-15 — reactive companion 0.6.0 candidate; see section 13 and `rebuild/docs/REACTIVE_COMPANION_0_6_0.md`.
**Owner decision:** ONE active development branch: `main`.
**Repository:** `neoncrucible/StackChanSource`
**Promoted source head (pre-documentation):** `4a0a816a0442f391533591db52b5a82a58bc1bad` from `kadence/sticks3-remote`.
**Previous main:** `3b9890063b3abe03e96cf2b00c1b94409532a8eb`; changed by a NON-FORCED fast-forward.
**Accepted fallback:** `kadence/baseline-0.4.13` at `1809efb48cfdd2356858e406486d19bccc2c03b6`.
**Target release:** host 0.6.0, "Reactive Companion".
**Status:** 0.6.0 Windows candidate built and verified; physical timing and owner acceptance pending.

## 0. Astra: read this first
Do not continue from the former `kadence/functionality`, `kadence/sensor-clean-base`, `kadence/sticks3-remote`, `kadence/rebuild-kade`, or any alpha branch. All new development must target `main` unless the owner explicitly changes this policy. Preserve existing commit SHAs and the 0.4.13 rollback package. Never assume that a code branch or passing CI reflects what is installed on the Windows computer. The owner wants one-shot, autonomous, fail-fast changes and only unavoidable hardware acceptance requests.

Do NOT resume the StickS3 microphone project, wireless CoreS3 link, gyro control, OpenClaw, or unrelated new models until asked. Do NOT flash CoreS3 for host-only UI/orchestration changes. Do NOT re-enrol saved native UnitV2 faces or reset camera features.

The normal robot is NOT a fully untethered mobile device: existing COM4/USB control tether persists, with LAN handling voice/media. Do not equate the StickS3 Wi-Fi remote with a wireless robot control/data transport.

## 1. Audited component inventory and evidence
| Component | Current source/candidate | Evidence and limits |
|---|---|---|
| CoreS3 firmware | 0.21.6 | Hardware-tested sensor/voice/body foundation. No new flash required for host changes. |
| Windows host | 0.6.0 candidate source | Continues main from f4ced1e. Natural camera commands, streaming warm-up and reactive tracking; see section 13. Installed Windows version and physical acceptance remain unobserved. |
| UnitV2 service | 1.3.0 | Factory Vision modes exposed; many physical mode tests still unproven. |
| StickS3 | firmware 1.0.3 candidate | Boot/pair/display corrections and driver fix recorded, but PTT still lacks successful hardware acceptance. Remote OFF. |
| Data | SQLite schema 5 | Native UnitV2 face files live on camera, not in PC SQLite backup. |
| Reasoning | Ollama qwen3.5:4b or configured Gemini | Exact installed model string matters; local reasoning does not make STT/TTS/offline vision local. |
| Speech | OpenAI STT + Sonia Edge TTS / local Windows fallback | User accepted the restored audio baseline (0.4.11); preserve existing speech output and cancellation. |
| Vision | UnitV2 native face recognition, greeting, snapshots, target tracker | 0.4.12 face/greetings physically accepted 2026-09-27. 0.4.13 object tracking reported working quite well. |
| Sensors | PaHub, PAJ7620U2 Gesture, VL53L1X ToF | Physically signed off 2026-09-17. ToF is range evidence, NOT person identity. |
| Motion | CoreS3 servo yaw/pitch and shared Home | Bounded ACK/torque-release, explicit arming. New cross-tab shared Home physical acceptance limited. |
| Utilities | Reminders, lab notes/workbench, calculations | Previous physical reminder checks; preserve states/DB. |
| Open known bugs | Volume slider/top-swipe; remote PTT | Do not silently mark fixed. Review volumes independently before closing. |

Pre-consolidation source check runs: `voice-alignment` and `sticks3` both succeeded (GitHub Actions run 36428902903); builds do not prove a live microphone or newly installed host.

## 2. Branch governance and archival inventory
As audited just before consolidation, 24 branches existed, including `main`. The source `main` now fast-forwards to the newest Kadence branch head. No historical branch ref has been deleted; the GitHub connector used for this audit cannot rename/delete Git branch refs. Only `main` is AUTHORISED ACTIVE. Any branch named below is read-only.

### Legacy branches whose content was already an ancestor of the promoted head
- `beta/project-kadence`
- `feature/alpha1-startup-foundation`
- `feature/voice-checkpoint-1`
- `firmware-dev`
- `kadence/baseline-0.4.13` — KEEP as recovery reference
- `kadence/functionality` — same SHA as baseline
- `kadence/rebuild-kade`
- `kadence/sensor-clean-base`
- `kadence/2.0-alpha-1`
- `kadence/2.0-alpha-2`
- `remote-dev`
- `kadence/sticks3-remote` — promoted source, FROZEN

### Diverged archival branches with unique commits NOT contained in promoted head
These are not current product work and must NOT be mass-deleted or mass-merged. Preserve their heads until their specific diffs are reviewed, then either tag/rehome necessary work or obtain owner's instruction to prune.
- `docs-dev` (1 unique commit)
- `feature/kade-eye-smoke-test` (5)
- `feature/kade-eye-v0.1` (18)
- `feature/kade-firmware-bootstrap` (4)
- `feature/optic-eye-checkpoint-0727` (23)
- `feature/servo-yaw-checkpoint` (16)
- `ios-dev` (1)
- `kadence/kade-work-shift` (6)
- `kadence/speech-diagnostic-20260908` (3)
- `kadence/2.0-alpha-3` (52)
- `server-dev` (1)

Counts are compare-ahead results against promoted `kadence/sticks3-remote`, not an assessment of useful uniqueness. Diverged branches may be obsolete upstream/vendor experiments. Preserve provenance; NEVER blindly merge them into current Kadence.

Obsolete open draft PRs at audit: #2, #5, #6, #7, #9 and #10. Closing a PR does not delete its head branch or merge its content. Treat closed PRs as historical references.

### Git workflow rule
- Use `main` as sole integration/development line, with tested, linear and reversible commits.
- Keep one canonical current-state document (THIS FILE), rather than another expanding chain of historical handovers.
- Preserve release SHA, matching host/CoreS3/UnitV2 versions, database backup path, hashes and rollback instructions.
- Never force push or overwrite an unverified owner's local changes. Check fast-forward state before writing.
- Change firmware only if necessary; otherwise update Windows host independently and validate existing 0.21.6 runtime.
- Future cleanup: after reviewing divergent branches, prune via GitHub branch-management UI/CLI only when authorised and after archiving their unique heads.

## 3. Architecture to preserve
- Device owns physical I/O, immediate feedback, hardware safety, touch/audio.
- Host owns identity, reasoning, utilities, perception orchestration and UI.
- `RuntimeBody`/`HostServer` keep one serial/control owner; voice audio runs on LAN.
- One camera producer lease; Privacy supersedes all camera requests, recording and cached preview. UnitV2 process stop is not electrical power-off.
- One movement lane with bounded `body.pose`, acknowledged completion and torque release; no duplicate servo writer or unsupported emergency-stop claims.
- Camera tracking and native face look are mutually exclusive; voice cancels/preempts where required.
- Recovery after disconnect, stale/malformed messages, startup state and cancellation must remain tested.
- Stored native UnitV2 face features cannot be recovered from SQLite alone; back them up on the device before modifying training/service.

Useful code starting points:
`rebuild/backend/kcore/desktop_ui.py`, `perception.py`, `reflex.py`, `sensor_sampler.py`, `occupancy.py`, `camera_manager.py`, `unitv2_lifecycle.py`, `motion.py`, `object_tracking.py`, `reminders.py`, `remote_server.py`, `runtime.py`; `rebuild/docs/NATIVE_UNITV2_FACES_0_4_12.md`, `OBJECT_TRACKING_0_4_13.md`, `FACTORY_VISION_0_4_15.md`, `STICKS3_REMOTE_0_4_14.md`.

## 4. Owner objective: make intelligence passive, not a maze of server tabs
The pre-M1 UI had six main pages and nine nested Vision tabs. Section 12 records the new four-page console source. DO NOT delete functionality; retain one service owner for actual behaviour.

Target product IA:
1. **HOME:** host/robot/camera/sensor health; actual last state; next reminder; recent meaningful events; clear stop/cancel, audio state, camera Privacy; single awareness selector OFF / EVENT_ONLY / AWARE.
2. **ACTIVITY:** readable event timeline with reason codes (e.g. suppressed due to voice busy, privacy, camera lease, cooldown), optional details, no raw sample spam or sensitive imagery.
3. **TOOLS:** reminders, project workbench, one-shot visual requests, explicitly armed object watching.
4. **SETTINGS:** display/audio, profile preferences, awareness quiet hours, thresholds, response policy. An intentionally collapsed **ENGINEERING** area holds UnitV2 training, LAB colour thresholds, manual pose/home, Factory Vision, Stick controls, transport setup, diagnostics.

Avoid multiple places controlling the same setting. Set `camera_policy`, `perception_enabled`, `privacy`, `greetings`, source and UnitV2 lifecycle through existing authorised services; read actual acknowledged state. No UI-only fiction. Existing voice commands invoke the same service, not parallel logic.

### Required passive behaviour semantics
- SensorSampler --> ReflexController --> PerceptionController --> action dispatcher: reuse this exact ownership chain.
- ToF occupancy: UNKNOWN/CLEAR/ARRIVAL_CANDIDATE/OCCUPIED/DEPARTURE_CANDIDATE. Arrival/departure hysteresis and distinct samples; stale evidence UNKNOWN, never departure.
- On eligible arrival in EVENT_ONLY/AWARE: one bounded local native UnitV2 face look; only greet upon confirmed eligible profile. One greeting per visit + existing per-person cooldown. Do NOT treat a ToF hit as identity. Unknown face notices remain opt-in and local.
- AWARE heartbeat during occupancy about every 120 seconds subject to budget; no repeated spoken commentary about idle desk.
- Background gestures: explicit whitelisted gesture-to-action mapping, not arbitrary text/model-driven servo commands. Default no unrequested motion. Priority order: privacy/safety > active voice/cancel > reminders > explicit vision > background awareness.
- Quiet hours, focus/do-not-disturb mode, cooldowns and energy limits. No repeated on-screen clutter.
- All hardware/camera/voice actions report actual results and explain why declined; no claims based on intent.
- Do not upload passive face frames or recognition vectors to cloud. Gemini on explicit descriptions only.

### Optional user-armed object watch — later milestone
"Tell me when this pen moves/disappears" must first arm a specifically selected ROI/object and record an initial state. Use factory tracker where viable, reject transient missing frames, detect sustained change and emit rate-limited event with evidence. A vanished MOSSE tracker is not proof of removal or theft. Expire, disarm, interrupt on Privacy/disconnect/voice and require explicit rearm for subsequent sessions. No automatic reacquisition claims.

## 5. Next release sequence for Astra — concrete deliverables and gates

### M0 — baseline and release integrity (PRIORITY P0)
1. Pull current `main`; record actual SHA and compare it with installed Windows app BUILD.json/RELEASE.json without requiring an unneeded flash.
2. Inventory device firmware 0.21.6, UnitV2 service 1.3.0, schema 5, configured provider, USB/LAN/audio modes, live sensor/camera state. Clearly mark UNKNOWN where not observed.
3. Safely back up PC SQLite including journal consistency; preserve native UnitV2 face features with their own verified on-camera backup and recovery instructions; do not overwrite previous fallback.
4. Run source, frozen-host, runtime ownership, privacy/cancellation, sensor coexistence and voice regression gates. Two green commit checks alone are not full acceptance.
5. Create a verifiable 0.5.0 candidate package only when all relevant gates pass, with hashes and no credentials.

### M1 — one practical console
**Source and Windows package gates passed 2026-10-13; physical acceptance remains pending (section 12).**
1. Build four-page IA above; old controls remain reachable under Engineering, with no layout duplication.
2. Real state labels and failure reasons, preference persistence, reconnect and tray behaviour.
3. Automated UI widget tests: privacy control, awareness modes, policy persistence, disabled controls during unavailable service, Voice vs camera arbitration, state after restart.

### M2 — passive coordination (core value)
1. Define a versioned `AttentionPolicy` or equivalent focused settings schema in existing storage; avoid another parallel controller.
2. Add quiet hours, do-not-disturb, greeting cooldown/visit logic, gesture whitelist, user-friendly event summaries and event dedupe.
3. Validate deterministic histories: >=30 min stationary user, depart/return, second person, UNKNOWN/stale sensors, interruptions, Privacy mid-capture, reconnection, battery/sensor failure.
4. Require 30–60 min physical desk soak: ONE greeting per legitimate visit, ZERO repeated greetings while seated, no unarmed head movements; conversation and reminder preempt background work; clean recovery.

### M3 — opt-in object watch (separate acceptance)
1. Start with static ROI and movement event, not inferred theft.
2. Follow with explicit disappearance watch only after recovery/stale/occlusion limits validated.
3. Prove bounded captures, storage/retention, acknowledgement, event logging and zero camera access when Privacy enabled.

### M4 — interim mobile chassis hardware branch of work (NO software branch)
Owner has an existing quarter-scale R5 shell as final body. Interim candidate preference: LAFVIN tracked tank platform. Solar tracker is a stationary pan/tilt donor, not locomotion. ESP8266 quadruped has 8 MG90 micro-servos and is a poor load-bearing platform for a top-heavy CoreS3 + camera + sensor hub. Tracked platform is simplest to ballast low and prototype differential drive, **but vendor payload/CG capacity is not verified**.

Astra MUST:
1. Measure actual existing robot + camera + cable/servo assembly masses, combined centre-of-mass height, R5 shell diameter/clearances, desired floor/desk use and battery envelope.
2. Obtain genuine tank chassis dimensions, material, motor stall current/gearbox torque, track clearance, safe payload and mounting hole locations; if unavailable, demand bench measurements and do not assert rated payload.
3. Prototype the tank with equivalent ballast low/high BEFORE mounting CoreS3/UnitV2. Check traction on indoor surfaces, turning, static/dynamic tip, motor/driver temperature, brownout and loaded runtime. Avoid snagged leads.
4. Mount battery and motor-control electronics near the bottom, CoreS3 and UnitV2 above, with protected cable routing, quick detachable adapter plate and mechanical service access.
5. Use a distinct drive MCU/motor driver and a versioned locomotion command interface; never reuse the servo yaw/pitch owner as wheel drive authority. A tracked Arduino controller may be a donor, not an intelligent Kadence host.
6. Motion defaults DISARMED at boot/reconnect; physical independent motor power kill, heartbeat/dead-man timeout, limited acceleration/speed, obstacle gating and tilt/stall monitoring. On any link loss motor command goes to zero. Keep rotation speed low with tall load.
7. USB-tether limitation: do NOT claim free roaming until wireless CoreS3 control replaces current serial dependency. First test a stationary tethered drive controller; later add safe LAN control with authentication and monitored link.
8. Plan modular adapter plate so the same locomotion module can be evaluated against the quarter-scale R5 shell. R5 integration is a distinct mechanical validation: compare shell base aperture, floor clearance, wheel/track position, centre of gravity and serviceability.
9. Do not spend engineering effort integrating vendor IR/app remote into the Kadence cognition pipeline. Keep native electronics only as necessary for an initial standalone drive test.

### M5 — physical presence and R5 fit
- Reuse current `body.pose` and physical movement arbiter for subtle low-frequency permitted head reflexes; no autonomous movement until shared Home/orientation and safe travel limits physically accepted.
- Confirm CoreS3 screen under proposed R5 eye/dome location, touch activator ergonomics, head camera field-of-view, cable strain, cooling, charging path and facial recognition distance.
- Keep rolling base independent from CoreS3 servo mounts; don't load the servo mechanism with shell weight.

## 6. Explicit done/not-done criteria
**DONE (prior owner evidence):** normal voice recovery, native UnitV2 face/greetings, ToF + gesture sensing, usable 0.4.13 object tracking, fixed post-answer head alignment.
**IMPLEMENTED but acceptance still incomplete:** 0.4.15 factory algorithm UI, shared Motion Home, Stick firmware mic correction.
**NOT DONE:** working Stick remote microphone, fully wireless robot transport, gyro motion, reliable opt-in object disappearance alarms, autonomous head reflexes, autonomous drive/R5 body integration.
**KNOWN regressions/issues to retain:** volume control defects and any physically unverified firmware features.

## 7. Astra report required after each milestone
Use a compact structured report: commit SHA + changed files, unchanged safety invariants, tests actually run (counts/links), hardware tests ACTUALLY witnessed vs pending, regressions, known limitations, installer/rollback pairing, and exactly one next operator task only if physical validation requires it. Never mark hardware PASSED from simulation. Record clear stop/rollback conditions.
---

## 8. Actual Kadence database — implemented, not aspirational (checked 2026-10-13)

**Critical: do not rebuild the database from memory or create a second SQLite file.** The exact source of truth for the CURRENT local schema is `rebuild/backend/kcore/schema.py`, currently `SCHEMA_VERSION = 5`. Schema migrations and DDL belong to `schema.ensure_schema()` ONLY. Confirm the version of the actually installed application before attempting a live migration. This inventory describes source on `main`, not a live dump of the owner's PC.

### 8.1 Current local topology and paths
```text
C:\KadenceX\source\                 # Kadence source/repo; NOT a runtime data directory
  rebuild\backend\kcore\schema.py   # ONE schema/migration owner
  rebuild\backend\kcore\storage.py  # ONE host-path/backup owner (KadencePaths)
  rebuild\backend\kcore\context_store.py
  rebuild\backend\kcore\utility_store.py
  rebuild\backend\kcore\perception_store.py
  rebuild\tools\storage_status.py
  rebuild\tools\package_firmware.py
  rebuild\tools\package_sticks3.py
  rebuild\tools\package_desktop.py
  rebuild\dist\                      # disposable BUILD outputs; not archival storage

%LOCALAPPDATA%\Kadence\               # default CURRENT runtime root
  database\kadence.sqlite3          # CANONICAL local SQLite DB, schema v5
  media\images\YYYY\MM\...png        # original user-saved image content on disk
  media\thumbnails\...               # bounded derived previews
  backups\                          # snapshots before migrations and manual backups
  exports\                          # user-initiated exports
  desktop-settings.json             # non-secret host UI config; root path retained for rollback
  desktop.lock                      # single-desktop guard
```
- An explicit `KADENCE_DATA_DIR` environment override changes the runtime root. Code MUST use `KadencePaths` rather than hand-built `%LOCALAPPDATA%` strings.
- Former `%LOCALAPPDATA%\Kadence\context.sqlite3` is a LEGACY location. `storage.py` has guarded migration and backups; if old and new databases both exist, refuse to guess/merge automatically.
- Images live on disk; `media.path` stores a **relative path**, checksum and metadata. It is not an image blob database.
- Native facial feature files remain on **UnitV2** and are NOT included in the Windows SQLite backup.

### 8.2 Current SQLite schema v5: 13 tables and responsibilities

| Current table | Important keys/fields | Ownership and use |
|---|---|---|
| `records` | integer `id`, `kind`, `text`, `created`, `done` | Legacy ContextStore notes/checklists; preserve for compatibility, do not create a new global memory store here. |
| `reminders` | integer `id`, `text`, UTC `due`, `timezone`, `state`, `kind`, `extra`, `robot`, `created`, unique `request_key` | UtilityStore, local scheduling/delivery/idempotency. Remains locally authoritative while offline. |
| `projects` | integer `id`, unique `name`, `created` | Lab/workbench projects. |
| `project_entries` | integer `id`, `project_id` FK, `kind`, `text`, `done`, `created` | Project notes and checklist steps. |
| `media` | integer `id`, unique `path`, `media_type`, `mime_type`, `source`, `captured`, image dimensions, `size_bytes`, `sha256`, `purpose`, `expires_at`, `pinned`, `deleted_at` | File metadata and retention flags; never store raw image bytes in DB. |
| `observations` | integer `id`, unique `media_id` FK, `project_id` FK, `question`, `description`, `qr`, `source_device`, `captured`, `created` | Explicitly saved project-related captures/description. |
| `persons` | UUID `id`, `display_name`, `greeting_name`, `active`, `recognition_enabled`, `greeting_enabled`, `enrolled_at`, timestamps | Kadence's local identity/greeting preferences; NOT yet the KadeHQ cross-app identity authority. |
| `face_profiles` | UUID `id`, `person_id` FK, `model_fingerprint`, `preprocessing`, `metric`, `embedding_dimension`, `embedding` BLOB, `reference_media_id` FK, `active` | PC legacy local face embeddings. Preserve compatibility; do not blindly transfer biometric vectors to HQ. |
| `perception_runs` | UUID `id`, `started_at`, `checkpoint_at`, `ended_at`, `end_reason`, config/model fingerprints | One bounded autonomous observation run, with crash/restart lifecycle. |
| `presence_sessions` | UUID `id`, `run_id` FK, nullable `person_id` FK, `identity_status`, visual evidence timestamps, `initial_trigger`, `ended_at`, `end_reason` | Observed individual/session evidence. ToF occupancy does not establish identity. |
| `perception_events` | UUID `id`, `event_type`, `event_version`, timestamps, `correlation_id`, run/session/person FKs, optional media/observation FKs, `camera_source`, `frame_id`, `trigger_type`, bounded `evidence_json` | Explainable, meaningful perception history; NOT a dump of every sensor reading. |
| `perception_actions` | UUID `id`, `presence_session_id` FK, person FK, `correlation_id`, `kind`, `state`, expiry/attempt/completion timestamps, `outcome`, unique session+kind | At-most-once greeting/unknown-notice intent. Recover ambiguous attempt as uncertain, never blindly replay. |
| `native_face_profiles` | `device_id`, `native_name` composite PK, `native_id`, unique `person_id` FK, `revision`, `available`, `synced_at` | **Metadata/link to UnitV2's on-board native identity files**; embeddings themselves live on UnitV2. |

**Schema lineage:** v1 `records`; v2 reminders/projects/project_entries; v3 media/observations; v4 person/legacy face/perception runs/sessions/events/actions + media retention; v5 native_face_profiles. New migrations must be additive, transactional, integrity-checked, foreign-key checked, backed up, and explicitly versioned from 5 upward. The exact DDL and constraints in source outrank the abbreviated table above.

**Current database access classes:**
- `schema.ensure_schema` — ONE owner of all migrations; do not run competing `CREATE TABLE IF NOT EXISTS` scattered through services.
- `storage.KadencePaths`, `storage.backup_sqlite`, `storage.connect_database` — path ownership, consistent committed-WAL snapshots, foreign keys ON.
- `ContextStore` — `records`.
- `UtilityStore` — reminders, projects, project entries, saved observations and media.
- `PerceptionStore` — persons, face profiles, native profile links, runs, sessions, events, actions.
- `DatabaseJobs` — bounded asynchronous job ownership during shutdown/cancel.

**Read-only operator check** (close Kadence/tray if planning the separately guarded `--upgrade` action):
```powershell
Set-Location C:\KadenceX\source\rebuild
uv run --no-project --python 3.12 .\tools\storage_status.py
```
Expected for a current successful source-layout check: `KADENCE_STORAGE PASS schema=5 integrity=ok foreign_keys=ok`. No upgrade, path migration or schema reset is authorised merely by updating this handover. Back up with SQLite's backup mechanism; NEVER copy a live database file alone and assume its WAL was captured.

### 8.3 Location of other state — not SQL rows
- Device firmware on CoreS3 is flashed to ESP32-S3 partitions; calibration/settings must survive upgrades. UnitV2 maintains its own native profiles and service payload.
- Config stays in `desktop-settings.json` and existing approved stores; API keys / Wi-Fi secrets belong in Windows Credential Manager or established paired-device secure storage, not JSON, SQL examples, repo commits, build logs, or diagnostic exports.
- Operator images/audio/raw recording payloads remain filesystem objects with database path/checksum references. Do not add raw firmware, camera frames, face-feature blobs, or hours of audio to a SQL table as a shortcut.
- An installed Windows executable/package is not the data root and is not a Git checkout.

## 9. KadeHQ / KadeLink / Kadence — agreed cross-project direction

### 9.1 Existing wider KadeSuite architecture (previously delivered, independent of this repo)
The KadeLink/KadeHQ project has a separately working v0.5.0 installation, distinct from the Kadence 0.4.15 source candidate. Earlier project handovers record:
- **KadeHQ:** PostgreSQL 18, database `kade_hq`, application role `kade_app`, pgvector 0.8.6. Logical schemas `shared`, `kadelink`, `kadence`.
- **Historical KadeHQ migrations:** `003_core.sql` initial core tables, `004` permissions work, `005_recording_dedupe.sql` for SHA-256 recording deduplication, and additive `006` for the working KadeLink v0.5.0 summary features. These are previously documented KadeHQ facts, **not independently re-inspected from its live PostgreSQL catalogue in this GitHub review**. Do not author another migration numbered 006.
- **Known logical tables:** `shared` identities, memories, embedding_models, embeddings and schema_version; `kadelink` recordings, transcripts, transcript_segments and sync_state; `kadence` events and reminders. KadeLink v0.5.0 also implements summaries, pin/keep, safe deletion, and summary/detail views; inspect its actual latest migration for the precise physical table/column names rather than inventing them.
- **Current workspaces:** `C:\KadenceX` (robot), `C:\KadePocket` (listener/Cardputer), `C:\KadeHQ` (central server/database/services, migrations and backups).
- **KadeLink pathway:** Listener / wearable or phone -> Windows transcription/processing -> KadeHQ canonical API and PostgreSQL -> Cardputer/Pocket as user interface/cache. Raw audio remains as referenced files. Future English translation should preserve original transcript, detected language and translated English independently, not destructively overwrite source text.

**Important phase boundary:** Kadence and KadeLink are NOT YET integrated. This subsection is a contract for future Astra planning, not permission to point Kadence directly at PostgreSQL or move SQLite today.

### 9.2 Intended source-of-truth split when integration is authorised

| Information | Current operational authority | Eventual cross-app owner / rule |
|---|---|---|
| CoreS3 / UnitV2 / Stick S3 state, safety and motor actions | Kadence host + respective device firmware | **Remain device/host local**, even after linking; KadeHQ must not become a realtime motor controller. |
| Local reminder due/delivery and in-flight action states | Kadence SQLite | Persist local due/delivery for offline guarantees; optional HQ mirror with stable IDs, idempotency, explicit conflict rules. |
| Face recognition vectors, native profile files | UnitV2 / approved PC legacy store | Stay at source by default. Link to HQ shared identity ONLY via non-biometric stable ID and explicitly consented metadata. |
| Local sensor, presence and greeting history | Kadence SQLite | Selected sanitized event summaries MAY sync to `kadence` schema with UTC, source ID and correlation ID; don't replicate routine frames/embeddings. |
| Shared person/identity and cross-app memory | Currently local to independent apps | KadeHQ `shared` becomes canonical for SHARED identity/memory when integrated; explicit local-to-global ID mapping; never guess identities from matching names. |
| KadeLink recordings/transcripts/segments/summaries | KadeHQ via KadeLink workflow | Remain under `kadelink` and shared memory APIs. Kadence gets authorised summaries/context via API, not SQL writes. |
| Firmware and desktop releases | Current source manifests and local/release artifacts | Central KadeHQ artifact registry is a **proposed** shared index, NOT yet an implemented database feature; actual binaries remain immutable files. |

Integration MUST use a **versioned KadeHQ API**, with service identity/authentication, explicit scopes, local caching, bounded timeouts, retry/backoff and service-offline fallback. ESP32, Stick S3, UnitV2, Cardputer and browser clients must **never connect directly to PostgreSQL**. Kadence must keep normal voice, physical safety, local reminders and camera behaviour operational if HQ fails.

Use an explicit integration adapter and incremental migration plan, not direct ad-hoc cross-database joins or two uncoordinated writable copies. Plan stable global UUID mapping and source-of-origin + correlation/request IDs. Handle duplicate delivery, reordered messages, deletion tombstones, replay suppression, retention and no infinite sync loops. During first rollout, start with **read-only shared summaries/context**, then **one-way sanitised Kadence event export**, then opt-in coordinated write paths only after ownership/conflict tests. Don't ingest KadeLink recordings/people/summary data into the Kadence persona without explicit product controls and privacy review.

### 9.3 Database design rules for Astra
1. Freeze and inventory both physical schemas first. For SQLite the schema source is `schema.py`; for KadeHQ capture `information_schema`/migration ledger from the actual installed v0.5.0 service. No speculative DDL based only on this summary.
2. Keep **one schema migration mechanism per database**. No runtime-created shadow tables, untracked SQL scripts, separate `kadence_new.sqlite` or `kadelink_test.db` in product paths.
3. Version API payloads separately from both DB versions; migrations and deploys need compatibility windows and rollback plans.
4. SQLite and PostgreSQL are not interchangeable database backends; if later consolidating selected records, design explicit export/transform/import/sync, never a blind file-copy migration.
5. Treat deletion everywhere as a coordinated API-level workflow with audit and tombstones; preserve user intent, retention policy, and UnitV2 onboard storage boundaries.
6. No credentials, raw face embeddings or unredacted transcription content in GitHub, CI annotations, firmware binaries, migration sample data or diagnostics.

## 10. Firmware / executable / release artifact policy — NO scattered binaries

### 10.1 Current tooling (implemented)
- `rebuild/tools/package_firmware.py` packages the **actual ESP-IDF `flasher_args.json` manifest**, validates ESP32-S3 target, flash file paths/offsets, startup-stack report where present, computes SHA-256 and writes a `RELEASE.json` next to the firmware package.
- `rebuild/tools/package_sticks3.py` produces `rebuild/dist/StickS3/kadence-sticks3.bin` and `RELEASE.json`, pins target firmware/protocol and verifies merged image components/ROM flash mode.
- `rebuild/tools/package_desktop.py` produces the frozen Windows host, `BUILD.json`/package `RELEASE.json`; it checks the source commit and checksum when bundling remote firmware. Host 0.5.0 M1 candidate retains CoreS3 0.21.6 compatibility and Stick 1.0.3 candidate; the Stick microphone remains unaccepted.
- `rebuild/dist` is an **ephemeral build output directory**, not a lifetime firmware archive. GitHub Actions artifact storage is also temporary; expiry must not make the only accepted rollback disappear.

### 10.2 Canonical release layout (PROPOSED, NOT YET DEPLOYED)
Use the existing KadeHQ system as the future **central KadeSuite artifact index**, never as a dumping ground for firmware BLOB columns. Start by agreeing its durable filesystem location; proposed structure for Astra to implement only after review:

```text
C:\KadeHQ\
  releases\
    kadence\
      cores3\<firmware-version>\<source-commit>\
        RELEASE.json
        manifest.sha256
        <verified ESP-IDF flash files and scripts>
      windows-host\<host-version>\<source-commit>\
        RELEASE.json
        <immutable installable package>
    kadelink\
      cardputer\<firmware-version>\<source-commit>\
        RELEASE.json
        <immutable target-specific image>
      windows\<version>\<source-commit>\
        RELEASE.json
        <immutable installable package>
    sticks3\<firmware-version>\<source-commit>\
      RELEASE.json
      kadence-sticks3.bin
  backups\                         # managed backups (not ad-hoc firmware ZIPs)
  db\migrations\                   # PostgreSQL schema migrations, not binary storage
```

This is a **proposed storage contract** only. Keep the installed `C:\KadenceX`, `C:\KadePocket`, `C:\KadeHQ` projects and current working packages in place. A final repository-specific KadeHQ release root and file permissions must be verified before implementing it. Other device families (UnitV2 service adapter, CoreS3 R5-specific builds, external drive MCU) will use explicit new target names, NEVER reuse an existing target's flash image.

### 10.3 Future KadeHQ release registry (PROPOSED schema design, no migration applied)
When authorised, inspect KadeHQ's actual DB/migration head (currently documented through migration 006). Create ONE additive migration, with review and rollback plan, introducing relational concepts **only if not already present**:
- **devices:** immutable `device_id`, stable hardware family/model, target identifier, capabilities, bootloader/protocol, physical unit/serial where non-sensitive, last observed firmware/host compatibility, health and revocation status.
- **artifacts:** artifact UUID, product/target, kind (firmware / host / bridge / release), semver/build, source Git SHA, CI run, immutable relative storage path/URI, byte size, SHA-256, build status and provenance; unique content hash plus safe target/version identity.
- **release_manifests:** versioned compatibility contract linking exact artifacts, supported host/device versions, DB/API/protocol ranges, flash layout/config, signed-off physical checks and rollback release.
- **deployments:** desired/applied release per device, timestamps, attempt ID, outcome, confirmed observed firmware, operator approval, recovery/rollback history. Never mark an artifact installed from merely downloading it.
- **migration ledger/sync queue:** reuse existing KadeHQ migration/version mechanisms and any existing queue; only introduce an outbox where a gap is demonstrated. No duplicate migration ledger invented alongside existing `shared.schema_version`.

Names are conceptual, **not assertions about already-existing tables**. Don't hardcode a new migration number until the current migration directory and live DB ledger are examined.

### 10.4 Non-negotiable release rules
1. Exactly ONE source path for each product/device target and ONE authoritative package builder. NEVER compile a firmware binary by dropping code into `desktop`, `docs`, `backups`, random project folders, a database, or a manual Downloads archive.
2. A release is an **immutable bundle** identified by target, version, Git SHA, build manifest, SHA-256 and explicit hardware compatibility. Any byte change produces a new release identity; no overwrite-in-place.
3. Target must match connected hardware. CoreS3 firmware NEVER flashed to StickS3 or Cardputer; UnitV2 service updates are NOT ESP32 flash images. Verify flash mode, partitions, memory map, offset and calibration preservation before flash.
4. Separate **build PASS**, **automated integration PASS**, **physical hardware PASS**, **owner acceptance**, and **installed/confirmed** in release metadata. CI success cannot fake a physical acceptance. Default release status must be `candidate` until explicitly accepted.
5. Preserve last accepted host, CoreS3 image, matching manifest, safe flash helper, data snapshots and rollback docs in durable storage before deploying a candidate. Keep source references and checksums. DO NOT prune the only rollback.
6. Never put a binary firmware BLOB in SQLite or PostgreSQL as the normal artifact store. The DB stores links, hashes, manifests, approvals and deployment history; the filesystem or durable artifact store holds the binaries.
7. Reject unknown/unregistered packages; validate source commit and checksum before installation/flash. No out-of-band flashing by a UI tab, background updater or separate bot without traversing this release gate.
8. Do not distribute hard-coded Wi-Fi passwords, API tokens, pairing secrets or personal/biometric data in builds or release manifests.
9. Publish release artifacts only from reproducible CI/build scripts; treat `rebuild/dist`, PlatformIO `.pio`, IDF `build` and local ZIP staging as disposable. Record the canonical durable release URI and install status.
10. The physical R5 body/drive MCU has its own board target and safety gate; it must not masquerade as or update the existing CoreS3 firmware image.

## 11. New required Astra gates for database and KadeHQ readiness

**Immediate (next Astra engineering session; read-only first):**
- [ ] Read `schema.py`, `storage.py`, `PerceptionStore`, `UtilityStore`, all packaging scripts and the live-app release manifest. Report exact schema/version, file paths, table counts, observed actual file versions, and backup health; do not infer a live DB's schema from code only.
- [ ] Inspect **existing KadeHQ PostgreSQL schema and migration ledger** from its own current source/service, and independently reconcile the documented `shared`/`kadence`/`kadelink` entities; do not add migration SQL yet.
- [ ] Inventory existing on-disk `C:\KadenceX`, `C:\KadePocket`, `C:\KadeHQ` release files **read-only**. Report duplicate builds and which exact checksummed packages are accepted. DO NOT mass-delete anything until accepted rollback paths are proven.
- [ ] Produce a single field-level **source-of-truth mapping** and proposed sync contract. Do not silently bind the Kadence runtime to HQ PostgreSQL.
- [ ] Produce an exact candidate artifact registry and release-directory migration plan with reversible copy+hash verification; only then request approval to relocate older packages.
- [ ] For every new DB migration, include transaction, row-count/foreign-key/integrity checks, live snapshot, recovery and one failed-upgrade test. For any firmware build, include target/offset/hash/compatibility/calibration/physical status checks.
- [ ] Update this SAME `KADENCE_CURRENT.md` with actual verified KadeHQ DDL/schema differences and accepted release paths when proved. Do not create a competing "handover-final-v7" file.

**Release acceptance:** Kadence normal operation still succeeds with KadeHQ fully unavailable; KadeLink transcription/summary data is preserved without duplicates; no unacknowledged command is replayed; no unexplained DB is created; every installed firmware has a trusted release manifest and an identifiable rollback; current UnitV2 face identities remain unchanged unless the owner explicitly authorises a retraining/delete operation.



## 12. Engineering continuation — 2026-10-13, M0 source / M1 console

**Audited starting SHA:** `3203c91f0741461cfc9329be6d3ec64628c18837` on `main`.
**Built implementation SHA:** `b17b42e00a9857fcb563e5a04181bd66246d83ff`.
The follow-up handover commit changes documentation only; the executable is built
from the implementation SHA above.
**Candidate host identity:** `0.5.0`; this is M1 progress towards Presence &
Consolidation, not a declaration that M2–M5 or physical acceptance are complete.
No firmware source, database schema, biometric profiles or HQ integration changed.

### Implemented changes
- `desktop_ui.py`: four primary pages, Home / Activity / Tools / Settings. Existing
  tools remain reachable. Engineering starts collapsed and uses one section picker
  for connection/provider credentials, UnitV2 lifecycle, perception checks, native
  training, face checks, Motion, Factory Vision, Stick controls and diagnostics.
- Home's sole awareness selector applies policy + perception opt-in together through
  the existing worker's `camera_patch`. It displays acknowledged configuration;
  refusal/timeout/disconnect do not claim success. A legacy policy with opt-in OFF
  correctly displays OFF. Privacy is an independent patch and remains accessible
  during voice and a pending awareness request. Manual camera controls respect
  privacy, active voice and service availability. Unrelated preference changes no
  longer resubmit stale privacy or awareness values.
- Actual live readiness remains distinct from saved settings. Stopping/disconnecting
  clears live sensor readiness labels. Tray reminder clicks open Tools / Reminders.
  `desktop_process.py` now reports a failed worker pipe write as unsent, so Home
  controls and camera requests cannot wait forever for an acknowledgement that
  cannot arrive.
  Profiles, native training, factory modes and explicitly armed tracking retain
  their existing service and storage authority.
- `tools/baseline_audit.py`: read-only operator inventory via `KadencePaths` and
  schema validation. It inspects schema version, all table/column names and counts,
  integrity/foreign keys, up to 20 newest SQLite backups, build/release identity
  agreement and complete package checksums. It rejects unsafe checksum paths,
  corrupt/incomplete packages and conflicting legacy/canonical DB locations.
  It does not create a database, migrate, copy releases, configure hardware or
  print record/face/credential content. Missing evidence remains UNKNOWN.
- `.github/workflows/kadence-functionality-host.yml`: restored host build/test
  triggering on sole active `main` instead of the retired development refs; added
  console and baseline-audit regressions. Existing Windows frozen executable,
  installer and voice/camera gates remain required. The unchanged Stick build is
  still an existing packaging dependency; this does not resume its mic development.
- Host version updated consistently in `pyproject.toml`, `build_info.py` and
  `package_desktop.py`; host manifests explicitly say candidate, schema 5 and
  physical sign-off false. Packaging provenance links now point to `main`.
  `DESKTOP_INSTALL_UPDATE.md` documents the new navigation and rollback boundaries.

### Verified locally vs still pending
- Linux source suite: **405 passed, 4 skipped, 119 subtests passed**, with the pinned
  face models and evaluation media hash-verified and enabled. The four skips are
  Windows-only firewall COM, Credential Manager, installer/shortcut and installed
  Windows speech checks; the Windows workflow covers them. A focused final
  console/audit/worker run also passed (18 passed, one Windows-only skip).
- `phase_a4_gate.py`: PASS — single runtime/voice owner, cancellation, reconnect,
  clean shutdown and preservation of post-voice head alignment in source.
- Qt offscreen widgets were rendered and inspected at 1160×800 and 980×690.
  This is layout/source evidence, not a Windows hardware acceptance.
- Added tests cover acknowledged modes, lifecycle rejection, Privacy while voice
  and awareness requests are active, partial preference patches, restart/voice
  persistence, offline controls, WAL-consistent read-only inventory, backup damage,
  manifest mismatch, path traversal, corrupt and incomplete package checksums.
- **CI / Windows executable: PASS.** [Actions run 38359902849](https://github.com/neoncrucible/StackChanSource/actions/runs/38359902849)
  tested the exact implementation SHA above. Windows: **336 passed, 81 subtests
  passed** across its six regression groups; runtime ownership gate PASS;
  `DESKTOP_FROZEN PASS` for the built executable's private worker, timezone,
  persistence, utilities, profiles/review photos/deletion, SQLite backup, camera
  voice status, vision history, local speech PCM and clean shutdown. Streaming
  decoding also passed. Live online speech and physical robot audio were NOT tested.
  The existing Stick packaging dependency passed its build/codec/merged-image
  checks; this is not microphone hardware acceptance. Physical sign-off stays false.
- **Windows candidate artifact:** `Kadence-Desktop-Windows`, artifact ID
  `11794611969`, 185,213,512 bytes. It contains
  `Kadence-Desktop-0.5.0-b17b42e00a98.zip`, with its own `SHA256SUMS`, BUILD/RELEASE
  identity and retained-version installer. Download from the Actions run above.
  GitHub's **outer artifact ZIP** SHA-256 is
  `9e06cff5cfd961e4d542361cf8437c9452c9024c36fb80e29e0b299b14dc76ec`.
  This is the outer Actions archive hash, not a claimed hash for the inner installer
  ZIP. GitHub reports expiry **2027-01-11 06:59:34 UTC**; this temporary candidate
  artifact is not the durable archive for an accepted rollback. No package was
  installed on the owner's PC in this session.
- **Not observed:** installed Windows BUILD/RELEASE identity; actual local DB row
  counts and backup health; native UnitV2 face backup; KadeHQ migration/DDL and
  KadePocket/HQ release files; hardware voice/camera/sensors/volume; physical soak.
  The source schema is still **5, thirteen application tables**. Do not report that
  as an inspection of the owner's live SQLite or PostgreSQL database.

### Safety, rollback and next work
One serial/control owner, one camera producer lease, privacy priority, bounded
movement/torque release, native UnitV2 identity ownership, local reminders, existing
voice cancellation and HQ-offline operation remain the existing architecture.
No remote microphone, wireless robot, locomotion, automatic head motion, new
model or KadeHQ migration was implemented. Known volume/top-swipe and remote PTT
issues remain open. The accepted recovery reference remains
`kadence/baseline-0.4.13` at `1809efb48cfdd2356858e406486d19bccc2c03b6`;
its actual durable package and data/UnitV2 backups still need Windows verification.

**One next operator task:** collect the M0 read-only inventory against the existing
Windows installation before installing the candidate. After updating the existing
source checkout from `main`, run in PowerShell:

```powershell
Set-Location C:\KadenceX\source\rebuild
$kadenceShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Kadence.lnk'
if (-not (Test-Path -LiteralPath $kadenceShortcut)) { throw 'Locate the existing Kadence shortcut before auditing; do not guess the installed version.' }
$kadenceInstalledDir = Split-Path ((New-Object -ComObject WScript.Shell).CreateShortcut($kadenceShortcut).TargetPath)
uv run --no-project --python 3.12 .\tools\baseline_audit.py --app-dir $kadenceInstalledDir
```

The report does not include native UnitV2 face files or live KadeHQ schema, and is
not deployment approval. Do not install if its layout conflicts or package hashes
fail, or if the accepted rollback cannot be located. Preserve all evidence and
resolve the specific mismatch first. After M0's remaining live evidence and M1's
owner checks, continue M2: versioned attention preferences, quiet hours,
do-not-disturb, visit/cooldown coordination and deterministic stationary-user tests,
then the required 30–60 minute desk soak. Do not add another controller or database.

## 13. Reactive companion continuation — 2026-10-15

The owner reported a serious latency/interaction regression after M1: slow voice,
slow UnitV2 preview, manual readiness gates, repeated target selection and a canned
recognition greeting. This priority supersedes the previous M2-only next-step list.
Host **0.6.0** continues `main` from `f4ced1e899b474ef7bcd89018b24afa80e51363c`.
It does not establish a new physically accepted baseline.

### Implemented

- Preserved the accepted incremental PyAV/PC audio route. The 0.5.0 diff did not
  remove it; do not invent that as the proven installed regression. Added two
  preloaded single-use speech children to remove repeated native import startup,
  earlier private phrase preparation and model/TTS overlap for robot/Both too.
  Robot/Both still require complete-buffer PCM under firmware 0.21.6. No wire change.
- Camera questions understand conversational wrappers and ordinary colour, shape,
  label and scene requests. Explicit tracking/factory requests perform readiness
  automatically, including when background mode is stopped or snapshot preference
  is the robot camera. Privacy and one camera lease remain mandatory. Saved automatic
  awareness triggers a bounded background readiness check without delaying voice startup.
- Local selection handles one unambiguous coloured region or moving foreground
  object for “track that”. Named objects retain Gemini selection. Ambiguity asks
  for clearer presentation rather than requiring a hand-drawn rectangle.
- Live tracking retains native JPEG and removes the added 150 ms polling sleep.
  Frame acquisition continues during a motor acknowledgement instead of freezing
  the preview. One in-flight step, no motor queue; Stop still drains the real ACK.
  The original 150 ms interval remains between completed head steps, independently
  of the preview, so the faster camera path does not increase servo command cadence.
  Voice keeps the visual target, pauses motor steps and drains any issued step.
  Brief loss can resume after three fresh, same-epoch, appearance-matched frames
  within five seconds. Larger jumps/long loss require another spoken request.
- One-time head setup is saved in `tracking-head.json`, bound to the shared home
  and only after movement/torque confirmation. Explicit subsequent follow requests
  automatically position and select; requests made during voice wait for its motor
  lane to release. Stop cancels queued requests. No unrequested idle motor motion.
- Home now focuses on conversation, one camera-request field, awareness and Stop.
  Privacy is global. Voice/connection settings are directly accessible. Speaker
  changes apply to the next reply without restarting. Existing preferences persist.
- Recognition greeting: “Alright, {saved greeting name}. What's the plan?”
- Added separate first-PCM, first-PC-playback, live-frame and target-selection
  timing evidence. No camera image, target name or spoken text enters timing logs.

### Verification and delivery

Clean local full-suite run with pinned face models/media on `4292c3d`: **453 passed,
4 Windows-only skips, 119 subtests passed** in 42.35 seconds. Runtime ownership/
alignment gate: **PASS**. Focused camera/UI group: **75 passed, 1 Windows skip**.
Final review also added a 250 ms first-use motion observation window: a brand-new
“track that” session must collect two frames before trying local selection, rather
than falling through to cloud recognition simply because it has only one frame.
Its real-process HTTP regression verifies cloud-free first selection. The Windows
frozen-package evidence is recorded below when complete. Do not confuse tests with
installed or physical acceptance.

See `rebuild/docs/REACTIVE_COMPANION_0_6_0.md` and the package's `WHATS-NEW.txt`.
CoreS3 **0.21.6**, UnitV2 service **1.3.0 source**, SQLite **5**, native face files
and the accepted **0.4.13** rollback remain unchanged. No reflash/re-enrolment is
required. Stick microphone, wireless control, locomotion and volume/top-swipe are
still outside this fix. Sessions still expire after 15 minutes; explicit snapshots
switch camera ownership away from tracking.

Consistent two-second audible replies, LAN camera rate and physical following are
not measurable from this build environment. After installing the complete candidate,
the next operator check is ordinary voice, “what colour is this?”, “track that”,
conversation while tracking, then Stop/Privacy. Use the new timing fields if latency
persists; do not ask the owner to navigate repeated readiness/arming switches.

### Final 0.6.0 build and download evidence

- **Package source:** `9336eefc8a05ab67e1c9a077f92cbbc962bb7622` on `main`.
  Implementation commits: `4292c3d` (natural requests, speech warm-up and console),
  `3d5593e` (first-use local motion selection), `be32f73` (continuous preview during
  head movement), `9336eef` (preserved motor settling cadence).
- **Clean full source suite:** `be32f73`, **455 passed, 4 Windows-only skips,
  119 subtests passed** in 42.83 seconds. Final cadence change then passed **41
  focused tracking/motion/appliance tests**; the exact final commit passed the
  Windows gates below. Runtime ownership gate passed locally and on Windows.
- **Windows CI:** https://github.com/neoncrucible/StackChanSource/actions/runs/38756179058
  — both jobs **SUCCESS**. The six Windows regression groups passed **386 tests
  and 81 subtests**. Packaged executable checks passed: incremental MP3 decoding
  (first PCM after 576 encoded bytes, before EOF), native speech-worker preload,
  local Windows voice, private worker protocol, database backup/profile operations,
  model/face replay, remote-off contract and clean shutdown. Online provider latency
  was not tested by the offline packaging gate.
- **Downloaded and verified artifact:** `Kadence-Desktop-Windows`, ID
  `11983798277`, contains **Kadence-Desktop-0.6.0-9336eefc8a05.zip**.
  Inner ZIP: **185,243,723 bytes**, SHA-256
  `0f8b5b51c3a840f88384f3e678281762e2b2d6ae16857a86bd8b5366379c8274`.
  All **1,173** manifest-listed files matched their SHA-256, with complete manifest
  coverage. Both BUILD and RELEASE identities matched source `9336eef` and host
  0.6.0; candidate status, no CoreS3 firmware and schema 5 were verified.
- **Outer Actions archive:** **185,243,913 bytes**, SHA-256
  `1e61a34fa411100c51d334744df576c956a1d0a0af7731a61003587e87ee072c`.
  GitHub reports artifact expiry **2027-01-13 14:58:25 UTC**. Preserve any accepted
  package durably; this temporary artifact does not replace the 0.4.13 rollback.
- **Installation:** quit Kadence, extract the complete inner ZIP and run
  `Install-Kadence.cmd`. No new CoreS3 flash, UnitV2 install or face retraining.
  This session did not install the package on the owner's PC or measure the actual
  robot's two-second response target, camera LAN latency or physical following.
