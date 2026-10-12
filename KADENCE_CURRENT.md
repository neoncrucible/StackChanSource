# PROJECT KADENCE — canonical state and Astra handover
**Audit date:** 2026-10-12 (Europe/London)
**Owner decision:** ONE active development branch: `main`.
**Repository:** `neoncrucible/StackChanSource`
**Promoted source head (pre-documentation):** `4a0a816a0442f391533591db52b5a82a58bc1bad` from `kadence/sticks3-remote`.
**Previous main:** `3b9890063b3abe03e96cf2b00c1b94409532a8eb`; changed by a NON-FORCED fast-forward.
**Accepted fallback:** `kadence/baseline-0.4.13` at `1809efb48cfdd2356858e406486d19bccc2c03b6`.
**Target release:** host 0.5.0, "Presence & Consolidation".
**Status:** engineering plan, not a claim of owner physical acceptance or deployed version.

## 0. Astra: read this first
Do not continue from the former `kadence/functionality`, `kadence/sensor-clean-base`, `kadence/sticks3-remote`, `kadence/rebuild-kade`, or any alpha branch. All new development must target `main` unless the owner explicitly changes this policy. Preserve existing commit SHAs and the 0.4.13 rollback package. Never assume that a code branch or passing CI reflects what is installed on the Windows computer. The owner wants one-shot, autonomous, fail-fast changes and only unavoidable hardware acceptance requests.

Do NOT resume the StickS3 microphone project, wireless CoreS3 link, gyro control, OpenClaw, or unrelated new models until asked. Do NOT flash CoreS3 for host-only UI/orchestration changes. Do NOT re-enrol saved native UnitV2 faces or reset camera features.

The normal robot is NOT a fully untethered mobile device: existing COM4/USB control tether persists, with LAN handling voice/media. Do not equate the StickS3 Wi-Fi remote with a wireless robot control/data transport.

## 1. Audited component inventory and evidence
| Component | Current source/candidate | Evidence and limits |
|---|---|---|
| CoreS3 firmware | 0.21.6 | Hardware-tested sensor/voice/body foundation. No new flash required for host changes. |
| Windows host | 0.4.15 source | Latest dated commit 2026-09-28, 4a0a816, UnitV2 LAB colour controls. Not fully owner-signed-off as one release. |
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

Latest commit check runs: `voice-alignment` and `sticks3` both succeeded (GitHub Actions run 36428902903); builds do not prove a live microphone or newly installed host.

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
The current UI has six main pages and nine nested Vision tabs. This is developer instrumentation presented as product UX. DO NOT delete functionality; restructure navigation and centralise actual behaviour.

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
