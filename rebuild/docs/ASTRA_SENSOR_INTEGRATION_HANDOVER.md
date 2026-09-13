# Kadence clean-base handover for Astra

Date: 2026-09-13

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
- app-based volume control works.

Known non-blocking issue:

- top swipe volume did not respond in the first physical test;
- this is lower priority than keeping the clean sensor base because volume remains controllable from the app;
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

## 5. Purchased Mk II sensor/vision hardware to integrate

The next hardware batch contains five modules.

### A. UnitV K210 AI Camera M12 Version (OV7740)

Purpose:

- dedicated edge-vision coprocessor;
- person/face/object detection and tracking;
- basic visual/gesture classification close to the device;
- offload vision work from the CoreS3 and avoid making normal voice/UI responsiveness depend on heavy image processing.

Integration goal:

Treat UnitV as an external vision source/coprocessor. Verify the exact transport/protocol for the installed UnitV firmware before writing the driver. Keep the existing camera/vision path functional while UnitV support is introduced; do not replace the current path until the external pipeline is independently proven.

Expected high-level outputs should be compact events/metadata rather than raw image traffic through the normal control lane where possible, for example detected class, confidence, position/region, person-present state or tracking coordinates.

### B. ToF4M distance unit (VL53L1X)

Purpose:

- accurate short-range distance/proximity measurement;
- allow Kadence to know when a person/object is close;
- support awareness of an object being presented in front of her;
- future use for approach/reaction logic and mobile-platform collision/context sensing.

Integration goal:

Expose a stable distance reading plus thresholded events such as near/clear rather than scattering raw range checks through presentation or voice code. Sensor polling must never block the voice lane.

### C. I2C Hub 1-to-6 Unit (PCA9548AP)

Purpose:

- six-way I2C expansion/multiplexing;
- allow multiple sensor units to coexist cleanly;
- isolate channels and reduce address-conflict problems;
- become the foundation of the Mk II sensor bus.

Integration goal:

Implement the hub/bus abstraction first. Put sensor discovery, channel selection and failure isolation behind one small hardware layer. A missing or failed sensor must not stop boot, voice, UI or the other sensors.

### D. Gesture Unit (PAJ7620U2)

Purpose:

- local hand-gesture recognition;
- immediate speech-free interaction;
- future mappings such as wake/attention, dismiss/cancel, next/previous or user-defined actions.

Integration goal:

Expose gestures as generic input events. Do not hard-wire gestures directly into the voice worker or reuse the old game-input architecture. Gesture mappings should live above the low-level sensor driver and remain configurable/testable.

### E. ENV III Unit (SHT30 + QMP6988; identity check required)

Correction from M5Stack's official ENV comparison on 2026-09-13:
ENV III uses SHT30 + QMP6988, ENV II uses SHT30 + BMP280, and the original
ENV uses DHT12 + BMP280. The previous heading combined different generations.
Verify the actual unit label before selecting a measurement driver.
QMP6988 defaults to `0x70`, which conflicts with a PaHub at `0x70` even behind
the mux. Resolve the physical hub address (for example `0x71`) and match the
firmware configuration before attaching an ENV III.
Source: https://docs.m5stack.com/en/unit/envIII

Purpose:

- temperature context;
- humidity context;
- atmospheric-pressure context;
- give Kadence environmental awareness for conversation, status reporting and future automation/personality behaviours.

Integration goal:

Produce a coherent environmental snapshot with timestamps and validity/error state. Environmental polling should be low priority and must not interfere with touch, audio, camera or conversation latency.

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

1. ENV III.
2. ToF4M.
3. Gesture Unit.

For each module:

- driver/init;
- non-blocking or appropriately scheduled polling;
- health/error state;
- device-status exposure;
- focused tests;
- physical sign-off before moving to the next module.

### Phase 3 — UnitV K210 vision

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
- desktop/app volume: PASS;
- top swipe volume: currently FAIL/non-blocking;
- clean-base objective: PASS for proceeding to sensor integration.

Astra should rerun the repository's existing gates plus new focused sensor tests after each stage, then perform a physical smoke test on the CoreS3 before considering that stage complete.

## 10. Immediate instruction to Astra

Start from `kadence/sensor-clean-base`, not from the older `kadence/rebuild-kade` state.

First inspect the current clean branch and this handover. Then design the sensor bus/event boundary before implementing device-specific behaviour. Preserve the now-working physical voice path as the highest-priority regression constraint.

The first coding milestone should be: **PCA9548AP hub + sensor discovery/health framework with zero regression when no Mk II sensors are attached.**

## 11. Phase 1 continuation — 2026-09-13

The next candidate is firmware `0.21.3`, based on this branch's `5771a00`.
The external Port A bus worker, PCA9548AP isolation, bounded discovery/health
snapshot, `sensors.status` protocol, typed host reader, and diagnostic are now
implemented. See [Phase 1 architecture and physical check](SENSOR_BUS_PHASE1.md).

Local host and native gates pass. CI must validate the firmware build and linked
stack budget before flashing. Physical testing of this candidate is still
pending; the earlier physical PASS in section 3 applies to `9091e7e2112b` only.
Do not begin ENV measurement integration until Phase 1 has physical voice and
empty-hub sign-off. Preserve all section 8 requirements.
