# Kadence integration handover for Astra

## Current continuation — 26 September 2026

Active work is on `kadence/functionality`, firmware **0.21.6**, schema **4**.
The owner accepted host **0.4.3** voice responsiveness. Preserve that voice
pipeline and home alignment; latency tuning is parked until camera/perception
and then tools are complete.

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
