# Kadence integration handover for Astra

## Current continuation — 26 September 2026

Active work is on `kadence/functionality`, firmware **0.21.6**, schema **4**.
The owner accepted host **0.4.3** voice responsiveness. Preserve that voice
pipeline and home alignment; latency tuning is parked until camera/perception
and then tools are complete.

### Immediate voice outage — host 0.4.11

The owner uploaded the 26 September 20:55 UTC diagnostic and then said voice
is not working. Runtime was cde2a47 / 0.4.10. Four connection attempts appear,
no recording/provider/completed-turn events, and `tcp-connect` code 116 at
20:54:13 UTC. USB recovery reported ready at 20:54:35; this proved only serial
reconnection. Do not claim that voice worked afterward. No new panic was recorded.

0.4.11 prioritizes audio restoration: Overview has an authenticated, no-microphone
two-tone Test Audio Link, read-only Windows network inspection and an explicit
Allow Robot Audio action. The elevated helper only updates Kadence's own app-path
TCP rule on Private/local-subnet networks. Public/global settings and unrelated
rules remain unchanged. Existing versioned installs use different executable
paths; stale firewall allowances are a credible cause, not proven by this export.
Automatic address selection can prefer physical Wi-Fi over VPN/UnitV2 USB routes;
explicit addresses remain authoritative and are checked for local assignment.
Alerts, greetings and snapshots also refresh the endpoint. TCP failures with
confirmed release no longer reboot otherwise working USB; Wi-Fi/device stalls
retain the supervisor. Alert/playback waits now share bounded voice deadlines.
Diagnostics distinguish cancellation and configuration evidence from confirmed
audio playback; no IPs, SSIDs, paths or credentials are exported.

Local: **330 tests / 119 subtests passed**, four expected Windows-only skips;
ownership/alignment gate passed and Overview checked at 980×690. Windows release
evidence is pending. See VOICE_CONNECTION_0_4_11.md for checks and limitations.

Separate unresolved enrollment evidence from the same export: 120 enrollment
records; best progress 9/20 at turn_other. No saved event. All 40 test and 18
automatic records have samples=0; 43 usable-face records say no_profiles.
First attempt detected two faces (not proof of two actual people). Do not blame
lighting or reduce match thresholds. The strict all-or-nothing guided training
needs a usable save/refinement path and exported rejection codes/pose evidence.
The log currently says capturing for every training frame, hiding why progress
stalled. Recognition/greeting acceptance remains open; scene descriptions accepted.

### Released — live recognition, host 0.4.10

The owner now confirms “what can you see, with description works flawlessly.”
Record scene descriptions as physically accepted. The owner's live recognition
and greetings remain unaccepted, despite earlier static successes. Do not equate
factory UnitV2's displayed 90% with SFace cosine scores or dismiss that the factory
live enrollment handles the owner's movement better than three Kadence stills.

Diagnostics from 26 September 19:45 UTC (runtime 9628a9b) show eight accepted
looks, four completed, two explicit cancellations and two missing terminal results;
health stayed processing with the last capture 267 seconds old. Five voice turns
completed and all three scene descriptions returned text. No new firmware/audio
fault was recorded. The old analysis returned silently if voice became busy
between frames, leaving processing/accepted state stale.

0.4.10 implements 20-sample, five-view guided live training with a same-page
preview, measured coverage, distinct-sample filtering, a fixed identity anchor,
120-second bound and atomic replacement. Three opt-in review photos remain
representative front/side images; old samples and photos survive failed training.
The camera stays leased, renews through captures and is source-pinned. No service
reinstall or firmware/schema change. SQLite's old 96-row read limit expands to
32 × 24 samples so later profiles do not silently disappear.

Matching keeps cosine 0.55 / margin 0.08, uses up to six fresh frames and requires
two of the last three associated observations, including a current match. Short
misses and differing trained views can recover without the old pairwise 0.65
veto. Conflicts/duplicate candidates remain ambiguous. A 20-frame explicit live
check never sends greetings. One budgeted follow-up can revisit an unrecognised
arrival during the same occupied visit. Every started automatic look terminates
with completion, cancellation or failure; voice and privacy retain priority.

Real-model checks exposed contrast-dependent false blur rejection: normalized
sharpness replaces the absolute 20 cutoff, with flat/soft crop rejection retained.
Detector confidence is 0.8, enrollment starting view requires 0.9 and >=64px width,
recognition requires >=40px. Identity thresholds are unchanged. Diagnostics add
only numeric/enumerated recognition evidence; no names/images/embeddings.

Pinned OpenCV replay uses disjoint frames: broader training matched 16/16 held-out
usable views locally versus 14/16 with three frontal prototypes; two other-person
controls stayed unrecognized. This is a small regression fixture, not a deployment
accuracy claim. The actual Windows executable must pass the same replay.
See LIVE_FACE_TRAINING_0_4_10.md for controls, limits, sources and acceptance.
Local verification: 321 tests passed, 119 subtests passed, three expected Windows-only skips.
The runtime ownership/alignment gate passed. Windows release evidence:

- Runtime source: `cde2a47ff45792eda9c1e81f00ee412d4fcb416b`.
- Windows run **36269318743**, job **108480108003**, conclusion **success**.
- **251 tests / 81 subtests**: camera/perception 125/26, reflex 22, autonomous 18,
  voice/recovery 65/41, speech 21/14. Ownership/alignment gate passed.
- Actual executable: 770 video frames decoded, 17 training views, 16 held-out
  views, 16 matches versus 14 with three frontal prototypes, two different-person
  controls rejected and four dim views usable. Native loader output is separated
  from a tagged replay result; earlier untagged console parsing failed the gate.
- Frozen speech generated 119360 PCM bytes; streaming decode emitted audio before
  EOF. Modern scene-description parser, models, profile/photo/delete/backup/IPC
  and clean shutdown checks passed. No live provider keys or physical robot here.
- Download (182563820 bytes):
  https://github.com/neoncrucible/StackChanSource/actions/runs/36269318743/artifacts/10914857905
- Artifact SHA256:
  `ae1cec5abee806c4df457ee53cf1f03443e5044020f2c53e29a203d6f9434c18`.

Install using the existing shortcut/installer workflow, verify **0.4.10**, then
select the saved profile → REPLACE SAMPLES. Complete the five-view live guidance
until 20 samples save, run LIVE RECOGNITION CHECK while turning/sitting normally,
then use TEST AUTOMATIC EVENT with Automatic Perception and Greetings enabled.
No firmware flash or UnitV2 service reinstall. Do not manufacture recognition or
greeting hardware sign-off from the replay: normal-use acceptance remains open.

### Released — descriptions and recovery, host 0.4.9

The owner asked for production quality after 0.4.8 improved recognition but still
needed a restart for audio and returned no scene descriptions. Latest screenshots
show one usable face, an identity match, two completed automatic bursts and a
delivered greeting. Do not repeat the private profile name. Latest diagnostics
show `tcp-connect` code 116 before recording, then two completed voice turns
after a server restart. Both voice looks obtained UnitV2 frames.

Root defect in description code: `vision.describe_image` read the removed Gemini
`outputs` response. Current Interactions uses `steps/model_output/content`; the
new `vision_provider` adapter parses that contract, ignores thoughts/echoed inputs,
bounds the whole request and returns typed, sanitised failures to speech and UI.
No live Gemini key was available for testing; modern API fixtures now traverse
the complete normal voice/tool/HTTP/speech/ACK path instead of mocking description.

Voice has stage deadlines, immediate retirement after provider failure, and
rate-limited reconnect through the existing serial supervisor after LAN/device
stalls. No automatic microphone retry, question replay or unconfirmed history
commit. Auto LAN selection refreshes per attempt; an explicit address is retained.
Tests exposed a separate cancellation leak: awaiting utility metadata before
releasing a connection could strand a closed audio slot. Cleanup now releases
ownership synchronously; tracked SQLite workers settle before services close.

Overview separates ambient Attentive from Connecting Audio, protects active host
phase display from device polls, shows the endpoint/recovery result, and offers
cancellation. Vision starts with Look & Describe and a side-by-side actual image
and description. Source/setup controls follow below. Checked at 980×690.
Diagnostics coalesces polling and preserves 240 important events separately from
the 400 recent records. Both exports exclude image/text/key/profile contents.

Local gate: **306 passed, four expected platform/model skips, 119 subtests**.
The runtime ownership/alignment gate passes. Windows regression and frozen
executable packaging also passed on runtime commit
`9628a9bf2089e112a60328ae15375e3131db226f`:

- Windows run **36264044193**, job **108465176368**, conclusion **success**.
- **237 tests / 81 subtests**: camera 111/26; reflex 22; automatic perception 18;
  voice and recovery 65/41; speech 21/14. Ownership/alignment gate passed.
- The actual executable parsed the modern vision fixture (50 output characters),
  decoded streaming speech before EOF, generated 119360 bytes of Windows local
  speech PCM, and passed model/profile/photo/delete/backup/IPC/clean-exit checks.
  `online_speech_tested=0`; no live Gemini account or physical robot was available.
- Download (182543510 bytes):
  https://github.com/neoncrucible/StackChanSource/actions/runs/36264044193/artifacts/10913089516
- Uploaded artifact SHA256:
  `f5f27d9a17082016e397102c7295ab66429f0ad4be5d6013012c03758fa5fafe`.

Install: quit the old tray instance, extract the whole download, run
`Install-Kadence.cmd`, use the existing shortcut, verify **0.4.9** and start the
server. Existing profiles/photos and pairing remain available. Ask for a fresh
look and compare the spoken answer with Vision → Camera; then check ordinary
questions and touch cancellation followed by a new question. Physical acceptance
is outstanding; do not invent a user sign-off or move on to latency tuning.

See `PRODUCTION_HARDENING_0_4_9.md` for implementation, exact stage limits and the
short physical acceptance sequence. Host 0.4.9 has no firmware or schema change.
The earlier firmware I2C ISR crash remains a material physical limitation;
do not label the complete robot production-accepted from host tests alone.

### Reboot recovery and face review — host 0.4.8

Latest owner evidence: 0.4.7 screenshot shows one profile with 3/3 compatible
samples. Diagnostics show a CPU0 StoreProhibited at STT start, then an in-place
reboot without a USB disconnect. The host kept waiting for the old voice ACK,
blocking subsequent touches and perception. No lighting measurement was recorded.

0.4.8 implements active serial-session invalidation on reboot/reset/new boot-ready
markers, independent of diagnostic quota. Existing recovery cancels providers,
audio and the old turn, discards unfinished history and accepts a new session.
The actual crash maps to the firmware I2C receive interrupt. All executable ELF
sections were verified against the accepted binary. See
`FIRMWARE_CRASH_2026-09-26.md` for exact artifacts and mapping. Firmware remains
0.21.6: **this host update does not prevent the underlying I2C crash**.

Face check is a fifth Vision tab showing the actual explicit test/enrollment
frame, source/time and usable-face boxes. Feedback distinguishes no detection,
small/blurred faces, absent enabled profiles, low cosine score, ambiguity and
cross-frame disagreement. Similarity thresholds remain unchanged. The exact
phrase “switch to extra camera” now selects UnitV2 directly without model planning.

Profiles adds opt-in local review photos (off by default), three bounded crops
linked through existing schema-v4 `reference_media_id`/`media` metadata. PNGs live
under `media/face-profiles`. Existing embeddings cannot recreate old photos: use
Replace Samples with the checkbox on. Replacement is atomic for the samples and
photo links, failed replacement preserves old files/data, and replacement/delete
removes old references. Failed unlink is reported and retried on refresh; orphan
files after a process kill are cleaned after a one-hour grace period on profile
access. Database-only backups do not include the photo files. A rollback to 0.4.7
can read samples but cannot manage this new photo gallery/cleanup.

Temporary preview is explicit-only and clears on interruption/privacy/reset/close;
no automatic frames are retained. Photos, embeddings and names remain excluded
from diagnostic export. The accepted voice transport/output and UnitV2 service
are unchanged. No firmware flash or SQL migration is required for this package.

### Verified 0.4.8 release evidence — 26 September 2026

Runtime commit: `1bd1bddd88c24411e8f512ef357df499dbf1f92e`.
Windows run `36259629029`, job `108452847019`, completed successfully:
**219 tests / 65 subtests**, runtime ownership/alignment gate and packaged
executable checks. Frozen verification includes real model inference, large
three-photo IPC response, profile/photo deletion, SQLite backup, camera voice
status, activity reads, streamed decoding, installed local speech and clean exit.
Online speech generation is not exercised by that frozen gate.
Local full suite: **291 passed / 103 subtests**, four expected platform/model skips.
The gallery and Face check were visually inspected at 1160x800 and 980x690;
results remain above the complete image at minimum size. The photo checkbox and
Replace Samples controls remain visible without expanding an empty gallery.

Download (182525325 bytes):
https://github.com/neoncrucible/StackChanSource/actions/runs/36259629029/artifacts/10911738089
Uploaded artifact SHA256:
`e4128448e1a42b4f6c0fe481c31f65674a55d58ac38ca9478e84cb671377557e`.

Quit Kadence including its tray instance, extract the full download, run
`Install-Kadence.cmd`, reopen the normal shortcut and verify 0.4.8. No UnitV2
service reinstall, SQL migration or firmware flash is required. To add photos to
an existing profile: select it, check Keep 3 local review photos, Replace Samples.
Then use Test & Preview to inspect the actual selected camera and matching result.
Hardware face matching, greetings and recovery still require the owner's device.
The firmware I2C crash remains unresolved; do not claim the host package prevents
reboots. Any recurrence should be investigated from the verified symbol record.

### Authorized full console / voice update — host 0.4.7

The owner explicitly approved implementation after reporting that greetings were
checked but they could not tell whether a camera look occurred. Requested useful
voice controls and a full server update. Work is implemented and released; all
release gates passed. New physical acceptance remains outstanding.

- Vision has Camera, Perception, Profiles and Activity tabs. Automatic enable is
  prominent and selects EVENT ONLY from OFF. Switches save immediately. Source
  selection applies to voice, manual capture, enrollment and recognition tests.
- Existing schema-v4 SQLite is retained. Profiles exposes compatible/total sample
  counts, sample dates and per-person recognition/greeting switches. Rename and
  delete are available; replacement keeps old samples until three new samples
  validate/commit atomically. Enrollment progress and its result remain visible.
  A SQLite backup API action gives a consistent snapshot and reports its filename.
- Test Recognition uses two fresh local frames with automatic perception off,
  never creates a visit/greeting, and honors privacy/cancellation. Test Automatic
  Event submits a gesture through real gates, rate limits and greeting guards.
  Activity shows capture decisions, source, local results, greeting delivery and
  producer stop confirmation, with recent stored event/action metadata.
- Existing desk_look already used the selected camera. Common look/status/control
  phrases now bypass model planning. Camera status grounds hardware awareness;
  explicit controls share DesktopController settings/lifecycle authority. Model
  proposed writes require confirmation; voice never enrolls or deletes profiles.
  No second serial owner. Missing Gemini keys and Privacy give clear explanations.
- Identical settings saves no longer reset visits or cancel active media. Voice
  interrupts explicit enrollment/tests as well as automatic perception. Names in
  local UI/activity are excluded from diagnostic exports; no new photo retention.
- Tests cover database reopen, atomic replacement, backup/delete, two-frame local
  identity, ambiguity, cancellation, actual selected source, voice authorization,
  lifecycle/privacy and Qt tab feedback. The frozen executable gate also checks
  profile metadata, database backup, camera voice status and activity reads.

No firmware, UnitV2 service protocol, database schema, face thresholds, accepted
voice transport/output or servo alignment change. Tools/OpenClaw and latency
optimization remain later phases. The owner still needs to physically verify
recognition, automatic events/greetings and voice camera commands on the new build.

### Verified 0.4.7 release evidence — 26 September 2026

Runtime commit: `2535cdcb523665a2d029a8a76c83713e951066b5`.
Windows run `36256384633`, job `108443850809`, completed successfully:
**206 tests / 58 subtests**, runtime ownership/alignment gate, bundled face model
inference and packaged executable checks. Frozen checks explicitly passed profile
reads, SQLite backup, camera voice status, history, streaming decoder, local speech
and clean shutdown. Online speech generation was not exercised by that frozen gate.
Local full suite: **283 passed / 103 subtests**, four expected skips for Windows
credentials, installer, installed Windows voice and packaged face-model inference.
Qt layouts were inspected at 1160x800 and the minimum 980x690; all four tabs have
independent scrollable content, and the enable/test controls are visible.

Download (182507758 bytes):
https://github.com/neoncrucible/StackChanSource/actions/runs/36256384633/artifacts/10910966620
Uploaded artifact SHA256:
`695ef12f97f306b27861cc14b5fb125faad8e04a654ec88ef51d760ec76f5f2d`.

Install as a normal host update: quit Kadence including the tray, extract the full
download, run `Install-Kadence.cmd`, reopen the usual shortcut and verify 0.4.7.
Existing schema-v4 data and pairing are retained. A working paired UnitV2 service
does not need reinstalling; firmware stays 0.21.6. In Vision select the camera,
inspect Profiles, run Test Recognition, then enable Automatic Perception and use
Test Automatic Event. A repeated greeting can be correctly suppressed by the visit
or five-minute guard. Try voice "Camera status" and "What can you see?" (the latter
requires the Gemini image-description key, even with Ollama reasoning).

No new physical result has been claimed. Next acceptance is the owner's saved
profiles/recognition, actual event/greeting and voice camera checks. Keep 0.4.3 as
the accepted voice baseline and 0.4.6 as the previous host package. Future tools /
OpenClaw and further latency tuning remain subsequent work.

### Owner hardware observations and requested usability work — 26 September, 17:08 BST

The owner reports camera start/stop and Privacy worked. Record those checks as
passed at their stated scope only: the installed host version was not supplied,
and full restart, lease-expiry, enrollment or autonomous-perception acceptance
has not been reported. Enrollment was attempted but the owner could not tell
whether it saved; automatic perception controls could not be located. Do not
treat that as successful enrollment or assume a specific cause for the missing
control. The source for 0.4.5/0.4.6 includes the enable checkbox; layout versus
an older launched executable remains unverified.

The owner requests a dedicated saved-profiles tab and asks whether to create a
SQL database. The existing canonical SQLite schema v4 already stores persons,
face_profiles, presence_sessions, perception_events and actions. Default path:
`%LOCALAPPDATA%\\Kadence\\database\\kadence.sqlite3` (KADENCE_DATA_DIR can override
the root). Enrollment persists names plus three face embeddings atomically,
not photographs. The current UI only lists names in a dropdown and places
progress/result messages in the shared footer. The owner's database has not
been remotely inspected; saved profile count/success is unknown.

Recommended next scope, presented for advice rather than claimed implemented:
keep the existing SQLite database and existing data; make Vision use clear
Camera, Perception, Profiles and Activity tabs. Profiles should read the real
database, show name/compatible sample count/enrollment time/recognition state,
refresh automatically, and give an explicit saved-or-failed enrollment result.
Add a bounded explicit recognition test so validation does not require walking
out of the sensor zone. Preserve current profile data until replacement samples
are validated and committed. Perception needs a prominent enable control,
policy and plain-language reason when blocked. Camera retains the accepted
lifecycle/privacy controls. Activity should expose why an event captured,
deferred or was suppressed, and whether producer stop was confirmed. Show the
running build clearly and provide the database path and a consistent backup
action. Do not introduce new photo retention, import factory UnitV2 identities,
or switch database engines as part of this usability work. Tools/OpenClaw and
latency tuning remain subsequent phases.

### Setup repair — host 0.4.6

The owner's 0.4.5 setup reached SSH, then SCP failed with
`Couldn't open /dev/null: Permission denied`. The remote service installer had
not run. The earlier Wi-Fi bring-up recorded factory `/dev/null` as root:root
0660 and a temporary 0666 correction; persistence was never accepted.
Host 0.4.6 verifies the opened Linux null character device (major 1, minor 3,
no symlink) and restores standard 0666 permissions through sudo before copying
files. It verifies the m5stack user's read/write access before staging. This
runs for both install and restore, and makes no boot-script changes. Camera
service, recognition and accepted voice behavior are unchanged. The existing
0.4.5 package can be unblocked with the single PowerShell command documented
in UNITV2_LIFECYCLE.md, then SET UP UNITV2 can be retried. Physical acceptance
remains pending. Six new installer regressions and the twenty local lifecycle
tests passed locally. Windows run `36249427399`, job `108424556284`, passed
193 tests / 58 subtests, runtime ownership, and the real packaged executable
gates. Host 0.4.6 runtime commit: `d41c6872cf2779222d15084bb0f5ddc006b1acd0`.
Verified download:
https://github.com/neoncrucible/StackChanSource/actions/runs/36249427399/artifacts/10908029095
Uploaded artifact SHA256: `d5b1f72de7e08172e49eaa47a98fb0c54deaa21ac7b907b2de2673adaeacf3a8`.
Use 0.4.6 for setup with the automatic permission check, or repair the current
0.4.5 camera permissions and retry its setup. No fresh hardware acceptance has
been reported; resume TEST START / STOP after setup and the camera power cycle.

- **0.4.4**: UnitV2 producer lifecycle checkpoint, commit
  `70d896b4f4c72c349fb7dad9231e6b456c211edc`. Windows regression and real frozen
  executable gates passed. Artifact:
  https://github.com/neoncrucible/StackChanSource/actions/runs/36241332115/artifacts/10905609924
- **0.4.5**: explicit opt-in for event perception and sparse AWARE checks,
  layered on the existing SensorSampler / ReflexController / CameraManager.
  Local two-frame face recognition, once-per-visit optional greetings, bounded
  deferred events, privacy, cancellation and diagnostic decision reporting.
  Runtime commit: `82af99b2e7a2faaad86b4577d9c72e91b55b4fee`.
  Windows run `36243033611`, job `108407012243`: all gates passed, including
  187 tests / 58 subtests, runtime ownership, local model inference, and the
  real packaged worker / speech decoding / storage / clean-shutdown checks.
  Artifact (182483818 bytes):
  https://github.com/neoncrucible/StackChanSource/actions/runs/36243033611/artifacts/10906712848
  Uploaded artifact SHA256:
  `b52a28cad83810fb25857abaffb615e8976760624e28fbd842bd6d2541f2426e`.
  Install 0.4.5 directly to get both releases; keep perception unchecked while
  accepting the lifecycle. Preserve 0.4.4 as the lifecycle-only checkpoint.
  Windows HTTP reads explicitly poll cancellation, including while waiting for
  response headers. Socket shutdown alone failed the Windows cancellation test
  and is not relied upon. STOPPED mode survives unrelated settings changes.
- UnitV2 needs the reversible service setup in `UNITV2_LIFECYCLE.md`. This uses
  the unchanged factory camera binary and preserves the original service for
  rollback. No robot or camera firmware flash. The installer refuses unknown
  factory checksums. Actual producer exit is distinct from electrical standby.
  To return to the older 0.4.3 camera path, use the new setup tool's R option
  and power-cycle UnitV2 to restore its factory service before starting 0.4.3.
  Host 0.4.4 uses the same lifecycle service and does not need that restore.
- Physical acceptance of these two new releases remains pending. Begin with
  automatic perception unchecked, run TEST START / STOP, then follow
  `CAMERA_PERCEPTION.md`. The saved check is tied to the paired service. Old
  EVENT_ONLY/AWARE settings do not silently activate automatic captures.
- Next after acceptance: bounded physical reflexes / richer cognition as needed,
  then tools (possibly OpenClaw), then revisit voice latency. Do not silently
  add automatic LLM calls, camera images in storage, or servo movement here.

Install sequence: quit Kadence; extract the download until Install-Kadence.cmd
is visible; run it and open the desktop shortcut. In Vision use SET UP UNITV2
once, follow its SSH/sudo prompts, power-cycle UnitV2, and start the server.
Select UnitV2, leave automatic perception unchecked, and run TEST START / STOP.
Require two successful cycles and STOPPED / stop confirmed. Then enroll a face,
select EVENT ONLY, enable automatic perception and Apply & Save. Follow the
short physical checks in CAMERA-PERCEPTION.txt before enabling optional greetings
or progressing to AWARE. No additional source pull or PowerShell launch is needed.

## Historical sensor clean-base snapshot

The following records retain their original dates and acceptance scope. The
current continuation above supersedes their branch and release instructions.

Date: 2026-09-13

Latest physical results and owner sign-off are in sections 14–17.
The next ToF4M candidate and agreed integration order are in section 18.
Firmware `038f203` / `0.21.5` is now installed with source-run host 0.3.4.
The owner has signed off camera operation, including capture with the sensor
hub attached and capture after a completed voice reply. The Capture button may
need a second click to display the image; the owner accepts this UI issue and
explicitly requests leaving it unchanged. Section 17 supersedes earlier pending
camera checks; it does not claim unperformed sensor or reminder tests passed.
Use [Windows startup and test commands](SENSOR_WINDOWS_QUICKSTART.md).
The latest app-volume result is FAIL, reported by the owner as pre-existing.

## 1. Use this source as the integration base

Repository: `neoncrucible/StackChanSource`

Working branch: `kadence/sensor-clean-base`

Known tested source commit before this handover document was added:

`9091e7e2112bbdd9e08141196147ad9a8c2660d0`

That commit message is `Remove final LED Memory hooks from voice lane`.

Local checkout used for the successful physical test:

`C:\KadenceX\source`

Firmware package generated from the tested source:

`C:\KadenceX\source\rebuild\dist\Kadence-RC2-Firmware-9091e7e2112b`

PR used for validation: `#10` — clean sensor base against `kadence/rebuild-kade`.

Important: `kadence/rebuild-kade` remains the pre-cleanup base at `5b9c04035dbdf8bf72d7377595ba8922a1433169`. Do not start new sensor work from that older branch. Start from `kadence/sensor-clean-base` and preserve the behaviour described below.

## 2. Why this branch exists

The previous RC2-era update added useful UI, avatar, reminders, camera/device infrastructure and an LED Memory game. The game became coupled into the same voice/media lane and front-touch routing used by normal conversation. The requirement was to create a clean foundation for the incoming sensor package without rolling back the current visual design or useful services.

The cleanup was deliberately surgical rather than a rollback.

### Preserved

- Current terminal/signal avatar and presentation behaviour.
- Current Signal Console desktop UI.
- Reminders.
- Current voice framing, speech recovery and cancellation path.
- Front-touch voice request/cancel path.
- Camera snapshot/vision infrastructure.
- Generic LED strip support and presentation states.
- Generic three-zone top touch sensing.
- Volume, mute, brightness, quiet-mode and reverse-swipe settings.
- Device status/settings transport.
- Workbench/device utilities and future sensor-ready infrastructure.

### Removed

LED Memory was removed completely from the active product path:

- memory-game state machine and sequence logic;
- game start/stop/submit behaviour;
- game-specific device status fields;
- `game.start` / `game.stop` host commands;
- game UI buttons/status/sound controls;
- game-specific tests and manual sections;
- front-touch interception by game state;
- game acquisition of the voice lane;
- game-note playback from the voice worker;
- camera/reminder gating on active game state.

A planned quiz/prediction game was never shipped, so there was no runtime implementation to remove.

## 3. Physical test status after cleanup

The cleaned firmware built successfully, was flashed to the CoreS3/StackChan body and was tested physically.

Confirmed:

- device boots;
- current avatar/UI is retained;
- Signal Console launches;
- voice works again on the physical robot;
- app-based volume control was originally reported working at this checkpoint;
  the later owner retest reports a pre-existing failure (section 12). Do not
  treat this historical result as a current volume PASS.

Known non-blocking issue:

- top swipe volume did not respond in the first physical test;
- the later app-slider failure is also open; app control cannot currently be
  assumed to compensate for the swipe limitation;
- do not make broad touch/voice changes merely to repair swipe volume while integrating sensors.

## 4. Files most relevant to preserving the clean architecture

Firmware:

- `rebuild/firmware/main/top_controls.cpp`
- `rebuild/firmware/main/top_controls.h`
- `rebuild/firmware/main/top_logic.h`
- `rebuild/firmware/main/touch_voice_bridge.cpp`
- `rebuild/firmware/main/voice_turn_lane.cpp`
- `rebuild/firmware/main/device_status_payload.h`
- `rebuild/firmware/main/camera_capture.cpp`
- `rebuild/firmware/main/presentation.cpp`

Host/backend:

- `rebuild/backend/kcore/appliance.py`
- `rebuild/backend/kcore/device_control.py`
- `rebuild/backend/kcore/desktop_worker.py`
- `rebuild/backend/kcore/desktop_ui.py`
- `rebuild/backend/kcore/vision.py`
- `rebuild/backend/kcore/services.py`
- `rebuild/backend/kcore/workbench.py`

Tests/gates:

- `rebuild/tests/test_rc2_media.py`
- `rebuild/tests/top_logic_test.cpp`
- `rebuild/tests/control_frame_test.cpp`
- `rebuild/tools/phase_b_gate.py`
- `rebuild/tools/phase_a3_voice_wire_gate.py`
- `rebuild/tools/interaction_gate.py`

## 5. Actual hardware — corrected from owner photographs

The earlier shopping inventory was wrong. The owner has:

- PaHub six-channel I2C mux with three address DIP switches; tested at 0x70.
- Unit Gesture U127, PAJ7620U2, 0x73, on channel 0.
- Unit ToF4M U172, on channel 1; responding at 0x29.
- Unit ID U124: ATECC608B-TNGTLS secure element, not an ENV sensor.
- UnitV2-M12: Linux / SigmaStar SSD202D camera, not the K210 UnitV.

There is **no ENV unit**. Leave the hub at 0x70; the ENV III warning in the
old diagnostic is static advice, not hardware detection. Removed from the CLI.
Unit ID and UnitV2 remain disconnected. Unit ID needs a deliberate identity/key
use case; do not write or lock its security configuration as a discovery step.
UnitV2 needs a separately verified USB/network or UART contract, not PaHub I2C.

Owner physically confirmed Gesture detection (two fresh scans, zero errors),
then normal voice. With ToF4M added, channel 0 responded at 0x73 and channel 1
at 0x29, both with zero channel errors; normal voice again worked perfectly.
These are detection/coexistence results on firmware 0.21.3, not measurements.

## 6. Integration architecture requested

Astra should integrate these modules into the current clean build, not bolt them directly into unrelated runtime code.

Recommended ownership model:

1. **Firmware sensor layer** owns physical buses, channel selection, polling and local device health.
2. **Sensor/event model** converts hardware readings into compact typed state/events.
3. **Device protocol** exposes sensor state without growing ad-hoc JSON fields in unrelated voice/game structures.
4. **Host runtime** consumes sensor events and decides what is useful to conversation, tools, automation or UI.
5. **Desktop UI** may display sensor health/current readings, but the sensors must work without the desktop being open.
6. **LLM/personality layer** receives only relevant, bounded context rather than a continuous firehose of readings.

Do not make sensor activity share ownership of `g_voice_lane_busy`. Voice remains the voice/media serialization boundary. Slow sensor reads, polling, inference and retries must not hold or block it.

## 7. Suggested implementation order

### Phase 1 — bus and diagnostics

- Add PCA9548AP support.
- Add explicit sensor discovery/health reporting.
- Boot normally when no new modules are connected.
- Confirm existing voice/UI/camera behaviour is unchanged.

### Phase 2 — simple sensors

Integrate in this order:

1. Gesture Unit (the next candidate; fixed channel 0).
2. ToF4M distance readings after Gesture physical sign-off.
3. Unit ID only once its intended security role is defined.

For each module:

- driver/init;
- non-blocking or appropriately scheduled polling;
- health/error state;
- device-status exposure;
- focused tests;
- physical sign-off before moving to the next module.

### Phase 3 — UnitV2-M12 vision

- establish and document the actual UnitV transport and firmware contract;
- build a bounded receiver/parser;
- expose detections as typed vision events;
- keep existing camera snapshot path intact;
- add tracking/person/object context only after raw communication is stable.

### Phase 4 — behaviour and UI

Only after all hardware is stable:

- show useful sensor state in Signal Console;
- map selected gestures to actions;
- make proximity/environment/vision available to the host conversational context;
- add personality/reaction behaviours conservatively.

## 8. Non-regression rules

During sensor integration, the following are hard requirements:

- Voice must continue to work physically after every stage.
- Do not reintroduce LED Memory or any game-specific state.
- Do not reintroduce game state into `device.status`, camera gating, reminders or the voice worker.
- Do not roll back the current avatar or Signal Console.
- Preserve reminders.
- Preserve front-touch voice start/cancel behaviour.
- Preserve existing camera functionality while UnitV is added.
- A missing sensor must fail soft, not fail boot.
- Sensor polling/inference must not acquire the voice lane.
- Integrate and sign off one module at a time rather than landing all hardware in one opaque patch.

## 9. Validation baseline

Before the physical sensor work began, the clean host candidate passed the runtime check, Python test suite, Phase B gate and voice-wire gate. The firmware then built successfully after the final stale game hooks were removed.

Physical sign-off on the clean candidate:

- voice: PASS;
- desktop/app volume: originally recorded PASS; latest retest FAIL, reported
  pre-existing by the owner (section 12);
- top swipe volume: currently FAIL/non-blocking;
- clean-base objective: PASS for proceeding to sensor integration.

Astra should rerun the repository's existing gates plus new focused sensor tests after each stage, then perform a physical smoke test on the CoreS3 before considering that stage complete.

## 10. Immediate instruction to Astra

Start from `kadence/sensor-clean-base`, not from the older `kadence/rebuild-kade` state.

First inspect the current clean branch and the latest results in section 12.
The Phase 1 bus/event boundary is implemented; preserve it when adding
device-specific behaviour. Preserve the working physical voice path as the
highest-priority regression constraint.

The original first milestone was **PCA9548AP hub + sensor discovery/health with
normal operation when no Mk II sensors are attached**. Its measured outcomes
are now in section 12. Do not restart that implementation or infer an all-pass
result while the volume failure remains open.

## 11. Phase 1 continuation — 2026-09-13

Firmware `0.21.3` was implemented in
`a73c936da3e9305c06987c2e56bfe0fe61351161`, based on this branch's `5771a00`.
The external Port A bus worker, PCA9548AP isolation, bounded discovery/health
snapshot, `sensors.status` protocol, typed host reader, and diagnostic are now
implemented. See [Phase 1 architecture and physical check](SENSOR_BUS_PHASE1.md).

Local host and native gates pass. [CI run 149](https://github.com/neoncrucible/StackChanSource/actions/runs/34758311792)
passed the firmware build, linked startup-stack check, Windows host jobs and
Windows desktop packaging. Physical results for this candidate follow below;
the earlier results in section 3 refer to `9091e7e2112b`.
Preserve all section 8 requirements and retain the failed volume result when
assessing Phase 1. The inventory correction and subsequent attached-sensor results are in section 5.
No measurement driver has been physically qualified yet.

## 12. Owner hardware tests — 2026-09-13

Tested pair:

- Firmware: `0.21.3`, locally built from `a73c936da3e9305c06987c2e56bfe0fe61351161`.
  Build and flash both returned their `KADENCE_* PASS` markers; calibration was preserved.
- Windows: Signal Console `0.3.2`, CI package `Kadence-RC2-1d4db2820820.zip`,
  build commit `1d4db2820820a3f3e062d47b460fe9c2d2c4db85`.
  The CI merge tree equals the firmware source tree:
  `43e9b5a3cc60043dfcf1ca257210ddf97caa77d3`.
- Confirmed installed application:
  `C:\KadenceX\apps\Kadence-RC2-1d4db2820820\Kadence.exe`.
  The owner checked its sidebar build ID and confirmed Play Games is absent.
- Hub: factory `0x70`, upstream connected to the **red Grove Port A on the
  CoreS3 itself**, with all six downstream sockets empty. The blue/black body
  sockets were not used. ENV, ToF, gesture and external camera were not attached.

| Check | Latest result | Evidence / scope |
| --- | --- | --- |
| No-hub diagnostic | PASS | Fresh `absent`, sequence 1 then 2, hub errors 0; six unavailable channels, no responses, channel errors 0. |
| No-hub voice/avatar with the correct console | PASS | Three complete voice turns, cancel during a longer reply, then a successful new question. Owner: "working perfectly". |
| Empty-hub diagnostic | PASS | Fresh `ready`, sequence 1 then 2; six `ready` channels, no responses, all errors 0. |
| Empty-hub voice/cancel/avatar | PASS | Repeated voice turns, cancellation and the next question remained stable. |
| Empty-hub camera and return to voice | PASS | Vision Capture produced an image; the next normal voice question worked without a restart. |
| Empty-hub reminder | PASS | `Sensor test`, `in 30 seconds`; owner confirmed due state, one robot notification and no restart. |
| App volume slider | FAIL — reported pre-existing | Owner says the slider did not work before this update either. Root cause and exact failure mode remain unverified. |
| Hub removed, normal boot and voice | PASS | Stopped server, powered off, removed hub, restarted and received a normal spoken reply. |
| Top-swipe volume | Previously open; not retested | Keep separate from the newly recorded app-slider failure. |

The first diagnostic snapshot was `starting`, sequence 0, age 18780 ms and not
fresh in both runs. No-hub snapshots then became `absent` at sequence 1 / age
2273 ms and sequence 2 / age 2269 ms. Empty-hub snapshots became `ready` at
sequence 1 / age 1183 ms and sequence 2 / age 96 ms. The owner observed a restart
when opening the empty-hub diagnostic; these logs alone do not establish its
cause. No repeated restart was reported during the subsequent application tests.

An older RC2 executable in Downloads was initially opened and still contained
Play Games. Voice/cancel testing was repeated successfully after installing and
identifying the correct console. A Git pull or firmware flash does not update
an independently extracted Windows executable.

These results establish the bus, empty-hub and tested coexistence checks.
**They are not an all-pass Phase 1 checklist: app volume remains failed.**
Camera/reminder checks were performed with the hub attached; separate no-hub
camera/reminder checks were not repeated in this session. Downstream fault
injection, measurements and long-duration hardware testing were not performed.
Do not attribute or rule out a sensor regression solely from the volume report;
the owner's statement establishes that the symptom was seen before this update.

Next: test the candidate in section 13 with the corrected inventory in section 5.

## 13. Current candidate: Gesture, persona, provider selection and Windows audio

See [candidate setup and limitations](GESTURE_PERSONA_AUDIO.md). Owner requested
restoring the GLaDOS / Seven of Nine / Ghost-inspired sarcastic companion,
checking Ollama routing, and louder output. The tested 0.3.2 desktop hardcodes
GeminiThinker; it does not use the prior Ollama model. This is verified in source,
not inferred from voice timbre. The generic persona was also verified in identity.py.

The candidate is host 0.3.3 / firmware 0.21.4. Installation and partial physical
results are now recorded in section 14; full Gesture coexistence sign-off is pending.
ToF ranging and UnitV2 integration remain subsequent milestones. Volume slider
and top swipe failures remain open; Windows output is an additional audio path.

## 14. Gesture physical results and camera investigation — 2026-09-14/15

Installed source: `282316cac268de4236c06117630f8cc78f78695f`.
Firmware 0.21.4 built and flashed successfully with preserved calibration.
The owner uses the source-run host 0.3.3, not the earlier Downloads executable.

- Persona restored and explicitly approved by the owner.
- Ollama `qwen3.5:4b` installed in the normal Windows Ollama store; selected
  as Thinking provider. The adapter uses `think:false`. A standalone simple
  question took 0.42 seconds; this is not end-to-end robot voice latency.
- Windows speech output, cancellation/next reply, and one-shot reminders were
  physically confirmed on host 0.3.3 before the Gesture firmware flash.
- After flashing 0.21.4, `gesture_status.py` reported `ready; fresh=True`,
  event sequences 1 through 15, and directional flags. Initial mixed flags and
  reversed physical directions are not proof of final mounting orientation.
- Normal voice with Gesture active worked. A recorded turn took STT 2147 ms,
  reasoning 12356 ms, and TTS 10082 ms; latency tuning was deferred by the owner.
- **Camera capture is FAIL.** Do not advance ToF or call Gesture fully signed off.
  No tests of physical Bluetooth speakers or simultaneous Robot + Windows output
  have been established. Reminder delivery with the new firmware remains to retest.

Camera evidence (UTC; attachment filenames refer to owner exports):

| Report | Observation | What it establishes |
| --- | --- | --- |
| `Kadence-diagnostics(3).json` | Four Sep 14 captures fail with host `uplink/unavailable` and device `camera-capture`, code 0. Serial status continues. | Failed standalone capture after a successful voice turn; not a proven Wi-Fi failure. |
| `Kadence-diagnostics(4).json` | Sep 15 11:48:53 first camera request after boot, touch sequence 0; same failure at 11:48:59. | A preceding voice turn is unnecessary to trigger failure. |
| `Kadence-diagnostics(5).json` | Requested test with hub disconnected. Camera at 11:54:27, active at 11:54:29; device status unavailable 11:54:34–54; uplink timeout 11:54:41; idle status resumes 11:54:55. | Different failure: image timeout and loss of status replies. The export alone does not prove a reset or hang cause, nor physically verify the cable state. |

Source findings:

- Firmware `camera-capture` means the final `KDAK` was not received. It is not
  a sensor-specific failure code: `voice_lan_send_image` also returns success
  when capture fails but its four-byte `KDI0` notification is sent successfully.
- Host `read_image` used to collapse no-frame, invalid frame, and truncated
  transfer errors into `uplink/unavailable` in the exported report.
- SerialBodySession discarded all non-JSON logs, including ESP32 panic/reset
  evidence. No reset cause can be recovered from these existing exports.
- `camera_capture.cpp` has not changed since its original RC2 implementation;
  no specific hardware/root-cause fix has yet been established.

Host **0.3.4** adds bounded, typed `device_diagnostic` and `camera_transfer`
records. Driver messages export only an allowed component/category, numeric
sensor ID/reset code/CPU and up to 16 program-counter addresses. Raw serial text,
credentials, tokens, image pixels and conversation content are excluded. Serial
observations cannot dispatch commands or complete ACKs; at most 128 are emitted
per connection. Image reads retain their existing size/authentication/deadlines.
An interrupted read identifies its current stage and received byte count (data
stage); the associated runtime issue distinguishes timeout from cancellation.
This is instrumentation, **not a claimed camera fix**, and requires no reflash.
Validation: 114 Python tests passed, 2 skipped, 55 subtests passed; Qt was
exercised offscreen. Phase B, voice-wire and runtime setup gates passed. The
camera failure remains a physical investigation, not a simulated success claim.

Next physical check: quit the previous host, pull this branch, source-launch
host 0.3.4 with the hub still disconnected, capture once, and export Diagnostics
after at least 60 seconds so any late firmware reset/recovery is included.
Do not repeat the older 0.3.3 export without the additional instrumentation.

## 15. Camera firmware comparison and alignment candidate — 2026-09-15

`Kadence-diagnostics(6).json` confirms host 0.3.4 is installed. The GC0308 is
detected (PID 155 / 0x9b) at 12:57:10 UTC. At 12:57:13 the host receives `KDI0`
and records `image-header / no-frame`: acquisition failed before an image was
sent. Normal device status continues. The reset code 21 appears at 12:56:04,
before capture, and must not be described as a capture-triggered restart.

At the owner's suggestion, compare the last working release before attempting
broader camera changes. Between `a73c936` / 0.21.3 and `282316c` / 0.21.4, the
camera implementation, voice/media wire implementation, CoreS3 power/pin setup,
SDK defaults, pinned components, build script and partition layout are identical.
The firmware delta adds Gesture initialization/polling/protocol plus the version.

The owner flashed the saved `Kadence-RC2-Firmware-a73c936da3e9` bundle (all hashes
verified, app 1,056,128 bytes), kept host 0.3.4 and the requested disconnected-hub
configuration, then reported "bingo" when asked whether Capture produced an
image. This confirms the old firmware can capture with the current host. It
does not establish which new allocation or scheduling change triggers failure.
Leave that working firmware installed until the candidate is ready.

Source inspection identifies a concrete pre-existing DMA alignment mismatch:

- Kadence requested a 64-byte DMA burst and aligned its requested frame to 64.
- IDF 5.5.4's [DVP controller](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_driver_cam/dvp/src/esp_cam_ctlr_dvp_cam.c)
  allocates its separate warm-up/backup buffer using cache-line alignment before
  initializing the DMA channel.
- S3 [GDMA transfer setup](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_hw_support/dma/gdma.c)
  requires external-memory RX buffer alignment equal to the selected burst.
  [S3's GDMA definition](https://github.com/espressif/esp-idf/blob/v5.5.4/components/hal/esp32s3/include/hal/gdma_ll.h)
  enables this constraint. Its [default data-cache line](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_system/port/soc/esp32s3/Kconfig.cache)
  is 32 bytes; the committed defaults do not override it.
- A buffer at 32 modulo 64 satisfies that allocator's guarantee but violates
  the old 64-byte burst requirement. Additional allocations can expose the
  mismatch without a change to camera source. This is a source-based causal
  hypothesis, **not a measured address from the owner's failed capture**.

Candidate firmware **0.21.5** selects the burst from the configured S3 data-cache
line size, with compile-time checks for 16/32/64-byte lines and whole-frame
divisibility. Both the driver's backup allocation and Kadence's 64-byte-aligned
requested frame then meet the burst requirement. This is the only functional
firmware change from 0.21.4; Gesture remains enabled and camera startup, transfer,
cleanup, timeouts, voice and sensor scheduling remain as before.

Physical confirmation still required: capture on 0.21.5 with the same host and
hub disconnected, repeat captures, then reconnect the hub while powered off and
check capture plus Gesture/voice coexistence. Do not call the camera fixed until
those tests pass. The 0.21.3 fallback does not provide Gesture measurements.

## 16. Camera capture restored on 0.21.5; hub coexistence pending — 2026-09-15

Tested firmware source: `038f203eb094ac049db208fcc066327781d7a190`.
The owner built `Kadence-RC2-Firmware-038f203eb094`, then flashed successfully
with all four hashes verified (app 1,058,400 bytes). Calibration was preserved.
CI [run 153](https://github.com/neoncrucible/StackChanSource/actions/runs/34976516511)
passed firmware build/gates, Windows host checks on Python 3.12 and 3.14, and
Windows desktop checks/packaging. This does not substitute for hardware tests.

The owner launched the same source-run host 0.3.4, was asked to keep the hub
disconnected and capture before voice, then reported "seems to work again now"
and supplied `Kadence-diagnostics(7).json` (104 events). The export verifies the
host version but does not independently identify the flashed firmware or cable
state; those come from the preceding build/flash and instructed test sequence.

| UTC | Observation |
| --- | --- |
| 14:02:30 and 14:02:52 | Reset code 21 recorded during connection startup, with one connection-unavailable event between them. These precede both captures; startup reconnect behavior remains separate from camera acceptance. |
| 14:03:12–16 | Robot connects, reports booting, then idle. Touch sequence remains zero throughout the export. |
| 14:03:32–34 | First Capture detects GC0308 PID 155, receives metadata and all 153,600 image bytes, records `image-complete` and `image-ack`, then returns idle. |
| 14:03:59–14:04:00 | Second Capture again detects GC0308 and completes all 153,600 bytes plus acknowledgement. |
| 14:04:01–34 | Normal idle status continues; no reset, panic or capture failure is recorded during or after either capture. |

After the first capture, idle free heap is 8,253,380 bytes and free PSRAM is
8,225,004 bytes. Both return to those same values after the second capture.
This shows no additional retained allocation on that second capture; it does
not establish leak freedom over longer operation. The report contains no voice,
reminder or Gesture measurement test.

**Physical result: two standalone camera captures PASS in this test sequence.**
The alignment correction is supported by the successful comparison; the failed
backup-buffer address was not measured, so do not claim direct proof of that
address being the cause. Full sensor coexistence is not yet signed off.

Next: quit the host, power the robot off, reconnect the existing hub to CoreS3
red Port A with Gesture on channel 0 and ToF4M on channel 1, power on and launch
the same host, then repeat Capture. If that passes, verify Gesture measurements,
normal voice, cancellation/next reply and reminder delivery on 0.21.5 before
advancing ToF ranging. Standalone serial diagnostics require the host to quit.

## 17. Owner camera sign-off with accepted UI issue — 2026-09-15

Firmware remains `038f203eb094ac049db208fcc066327781d7a190` / **0.21.5**;
source-run host remains **0.3.4**. No further runtime change or reflash is needed
for this sign-off.

- After the instructed power-off hub reconnection and repeat Capture check,
  the owner reported "ok its fixed". Camera with the sensor hub attached is
  accepted as PASS. The instructed wiring is CoreS3 red Port A, Gesture on hub
  channel 0 and ToF4M on channel 1.
- With everything left connected, the owner was asked to complete a normal
  voice conversation and then Capture again. The owner replied "yes works
  perfectly", confirming both the voice reply and subsequent camera image.
- The owner reports that the UI Capture button seems to require a second
  press before an image appears. **Accepted known issue; leave unchanged at
  the owner's explicit request.** No cause for this display/click behavior has
  been established. Do not describe first-click preview behavior as fixed.
- The owner explicitly requested sign-off and a commit to the working branch.

**Camera regression: signed off by the owner, with the above UI exception.**
The disconnected-hub captures have diagnostic evidence in section 16; the
hub-attached and post-voice results are owner reports without a new diagnostic
export. Keep those evidence types distinct.

This closes the camera recovery work. It does not add new evidence for Gesture
measurement accuracy/orientation, cancellation/next reply or reminder delivery
on 0.21.5, physical Bluetooth output, or simultaneous Robot + Windows output.
Previously recorded results remain valid only for their stated test versions.
App volume remains the pre-existing open issue. ToF ranging and UnitV2 integration
remain subsequent work; neither is implemented or signed off by this entry.

## 18. ToF4M measurements candidate; UnitV2 follows acceptance — 2026-09-15

The owner explicitly requested: test and confirm ToF4M, then integrate UnitV2,
then confirm no conflicts before adding functionality. Gesture direction
detection was already confirmed; ToF's earlier 0x29 response was discovery only.

Candidate host **0.3.5** / firmware **0.21.6** adds the VL53L1X measurement state
machine, bounded shared-worker register traffic, validated cached `sensors.tof`
status and `tools/tof_status.py --gesture` for simultaneous observation using
one serial connection. The camera DMA alignment fix from 0.21.5 is retained.
Read [ToF4M bring-up](TOF4M_BRINGUP.md) for register sources, limits, cold-start
PowerShell commands, acceptance checks and the subsequent UnitV2 milestone.

Native coverage includes wrong chip identity (no configuration writes),
distance/quality decoding, boot/data-ready timeouts, result/clear failures,
isolation failure, quarantine/recovery and discovery plus Gesture/ToF scheduling.
Wire coverage checks the fixed channel/address query, mutation rejection, frame
capacity and age wrap. Host tests reject invalid types, impossible valid readings,
stale data and verify cached queries do not claim the voice lane. Firmware
packaging includes required sensor-driver notices with hashes.

Local validation: 118 Python tests passed, 2 skipped, 71 subtests passed;
Qt ran offscreen. The native sensor bus/protocol/Gesture/ToF gates passed with
AddressSanitizer and UndefinedBehaviorSanitizer. Phase B (45 checks) and the
voice-wire gate passed. CI must compile/package the ESP-IDF 5.5.4 candidate
before physical deployment; no local hardware test is implied by these gates.

**Physical ToF4M and coexistence sign-off: pending.** UnitV2 code is not changed
by this candidate. No sensor readings trigger actions, enter LLM context, or
change the avatar. Keep the current accepted Capture second-click exception
and pre-existing app-volume issue as recorded; neither is modified here.

## Camera/perception host candidate — 2026-09-22

Work continues only on `kadence/functionality`. Host 0.4.0 adds a single camera
owner, saved OFF/EVENT_ONLY/AWARE policy selector and privacy override, bounded
sensor-triggered local perception, explicit three-frame YuNet/SFace enrollment,
per-subject sessions and transactional optional greeting/notice delivery. Schema
stays v4 and firmware stays 0.21.6. No flash required. Defaults keep autonomy and
actions off. See `CAMERA_PERCEPTION.md` for capabilities, limits, model hashes,
rollback and one physical acceptance pass.

Local verification: 179 tests passed, four platform/model checks skipped, plus
78 subtests; phase_a4 ownership/reconnect/head-alignment gate passed. Windows CI
also verifies the downloaded model hashes, real local inference, executable
model loading, saved privacy, speech and clean shutdown. Owner acceptance of the
new policy/enrollment/autonomy behaviour is pending. Previously accepted manual
camera and voice behaviour remains covered; the onboard two-click quirk remains.
UnitV2 producer-off/sensor standby is still unsupported, not claimed by privacy.
