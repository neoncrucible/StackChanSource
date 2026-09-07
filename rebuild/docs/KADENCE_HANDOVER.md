# Kadence blind rebuild — restart-safe handover

**Repo:** `neoncrucible/StackChanSource`  
**Branch:** `kadence/rebuild-kade`  
**Workspace on user's PC:** `C:\KadenceX\source`  
**Firmware:** `C:\KadenceX\source\rebuild\firmware`  
**Hardware:** M5Stack StackChan / CoreS3 / K151, ESP32-S3  
**Normal serial port:** `COM4` at `115200`  
**ESP-IDF:** 5.5.4  

> This file is the authoritative handover for continuing the blind Kadence rebuild in a fresh chat. Read it before proposing work. Do not ask the user to reconstruct previous context unless this document is demonstrably insufficient.

---

## 1. What this project is

Kadence is intended to be an **embodied companion and home assistant**, not merely an ESP32 front-end to a chatbot.

The device owns physical I/O, local safety, immediate feedback and embodied presentation. The host owns cognition, memory, orchestration and integrations. Device and host communicate through a versioned protocol boundary.

The user explicitly gave Kade freedom to redesign the project from scratch as a **blind/no-spoilers rebuild**. Kade leads architecture and implementation. The user performs physical QA and pastes outputs but should not be asked to author code.

Preserve the blind-build spirit for unfinished areas. Do not spoil UI/avatar/personality surprises unless required for QA or the user explicitly asks.

---

## 2. Definition of finished Kadence

Do **not** call the overall project finished merely because transport, voice or runtime tests pass.

A finished build should provide:

1. intentional visual identity and avatar/presentation language;
2. local autonomous presence while idle;
3. personality/identity independent of the model provider;
4. natural voice interaction with cancellation and failure recovery;
5. safe embodied reactions using the proven body path;
6. controlled host-side tools and integrations;
7. useful companion/home-assistant behaviour rather than demo scripts;
8. durable context/memory where appropriate;
9. clean degradation/recovery from serial, provider and integration failures;
10. a normal daily-use runtime, not a pile of checkpoint scripts.

---

## 3. Non-negotiable architecture contract

`rebuild/docs/ARCHITECTURE.md` is authoritative. Preserve these invariants:

- Device owns physical I/O, local safety and immediate feedback.
- Host owns cognition, memory, orchestration and integrations.
- Device/host communication crosses a versioned protocol boundary only.
- STT, Thinker, TTS and ToolBridge providers remain replaceable.
- Kadence identity is independent of model provider.
- External integration failure must not prevent basic device operation.
- Long operations are cancellable and must not block presence.
- One physical movement lane at a time.
- Movement success ACK only after safe execution and torque release.
- Late ACKs after timeout/cancel cannot poison a healthy session.
- Correlation IDs never cross command lifecycles.
- Malformed/noisy serial must not wedge the host.
- Reconnect releases stale state.
- Do not introduce duplicate movement, touch, I2S/I2C or serial owners.

---

## 4. User workflow / operating rules

- Address the user as **Boss** during Kadence technical work.
- Kade leads the design and writes/commits code.
- Do not ask the user to edit code unless genuinely unavoidable.
- Keep instructions compact and direct.
- The user originally preferred one command at a time, but has explicitly approved **batched safe sequential commands**. Batch build/gate/flash/test steps when sensible and make them stop on the first error.
- Before meaningful local testing, pull/fetch current `kadence/rebuild-kade`; a stale-remote incident previously wasted much of a day.
- Do not casually clean generated/untracked firmware artifacts.
- Avoid redundant fullclean/build/flash loops.
- If a mistake is ours, own it and fix it ourselves.
- Do not imply background/asynchronous work.
- Keep API keys and Wi-Fi passwords out of chat. API credentials are environment-only unless a secure persistence solution is deliberately added later.
- COM4 is control-only. Audio data plane is LAN/TCP.

After a fresh PowerShell/reboot, activate ESP-IDF with:

```powershell
. C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1
```

Build/flash:

```powershell
cd C:\KadenceX\source\rebuild\firmware
idf.py build
idf.py -p COM4 flash
```

Generated/untracked local paths may include:

```text
rebuild/backend/kcore/__pycache__/
rebuild/firmware/build/
rebuild/firmware/dependencies.lock
rebuild/firmware/managed_components/
rebuild/firmware/sdkconfig
rebuild/tests/__pycache__/
rebuild/tools/__pycache__/
```

Do not delete them reflexively.

---

## 5. Runtime/body foundation — COMPLETE, DO NOT REOPEN

Checkpoint work through CP23 established and physically verified:

- v1 protocol envelopes and correlation IDs;
- bounded `body.pose` decoding;
- real physical movement through the proven motor path;
- calibration preservation;
- ACK only after physical completion and torque release;
- pending request lifecycle, timeout/cancel retirement and late-ACK hardening;
- presence/heartbeat not blocked by body commands;
- single-owner movement lock;
- real USB Serial/JTAG transport over COM4;
- HostServer -> COM4 -> firmware -> motor -> correlated ACK;
- disconnect/reconnect recovery;
- malformed/noisy traffic resilience;
- clean runtime ownership and shutdown.

Authoritative final foundation proof:

```text
CP23_LIVE PASS runtime_owner=1 sequential_commands=1 correlated=1 torque_released=1 clean_path=1
```

`rebuild/backend/kcore/runtime.py` / `RuntimeBody` remains the correct normal runtime foundation. Extend it; do not bypass it with a second body/control stack.

---

## 6. Phase A status

# Phase A — Presence, Identity, UI, Avatar, Voice

**Goal:** transform the proven chassis/runtime into recognisable Kadence.

### A1 — Display architecture + visual identity — COMPLETE

Implemented and live-proven:

- `rebuild/firmware/main/presentation.cpp`
- intentional presentation states including boot/idle/attentive/listening/thinking/speaking/tool/offline/degraded/fault/recovery;
- purposeful touch behaviour;
- local rendering independent of host latency;
- debug/probe infrastructure retained behind the product presentation rather than used as normal UX.

User visually signed off A1. Do not explain unrevealed presentation details unless needed.

### A2 — Presence engine + embodied behaviour — COMPLETE

Implemented and live-proven:

- `rebuild/firmware/main/presence_engine.cpp`
- local autonomous presence while idle;
- interaction pre-empts/yields presence;
- safe movement ownership and torque release preserved;
- presence remains local and independent of long host operations.

Final proof:

```text
PHASE_A2_LIVE PASS precondition=1 interrupt=1 command=1 correlated=1 torque_released=1 recovery=1
```

### A3 — Voice + personality loop — COMPLETE AND SIGNED OFF

A3 is fully live-proven as of 7 Sep 2026.

Host/provider stack:

- OpenAI STT model: `gpt-transcribe`
- Gemini thinker: `gemini-3.5-flash-lite`
- Edge TTS voice: `en-GB-SoniaNeural`
- identity/persona layer independent of provider;
- HTTP provider stack with cancellation/failure handling;
- no Ollama, Xiaozhi, Conda or FFmpeg dependency.

Audio/control architecture:

- COM4 remains control-only.
- Audio is a separate LAN/TCP data plane.
- Device sends 16 kHz mono, 60 ms Opus frames.
- Host wraps raw Opus packets into Ogg Opus for OpenAI transcription.
- Sonia MP3 is decoded/resampled in-process to 16 kHz mono PCM with `miniaudio`.
- Reply PCM is staged in CoreS3 PSRAM before playback.
- Actual I2S writes drain through internal DMA-safe RAM, eliminating network-fed speaker fragmentation.
- Wi-Fi credentials are RAM-only (`WIFI_STORAGE_RAM`) and are not persisted by firmware.
- voice turn runs on its own worker lane; one serial reader remains authoritative.
- pre-emptive cancel can interrupt blocked LAN I/O and local buffered speaker playback.
- no duplicate I2S/I2C/touch/serial owner.

Relevant current firmware modules:

```text
rebuild/firmware/main/voice_lan.cpp
rebuild/firmware/main/voice_cancel_io.cpp
rebuild/firmware/main/voice_playback_buffer.cpp
rebuild/firmware/main/voice_turn_lane.cpp
rebuild/firmware/main/touch_voice_bridge.cpp
rebuild/firmware/main/probe21.cpp
```

Relevant host modules:

```text
rebuild/backend/kcore/voice_providers.py
rebuild/backend/kcore/voice_wire.py
rebuild/backend/kcore/serial_transport.py
rebuild/backend/kcore/runtime.py
rebuild/backend/kcore/host.py
```

A3 live sign-offs:

Normal physical roundtrip, after fixing speaker fragmentation:

```text
PHASE_A3_ROUNDTRIP PASS stt=1 thinker=1 tts=1 device_mic=1 opus=1 device_speaker=1 correlated=1 body_command=1 torque_released=1 recovery=1
```

User explicitly reported playback **smooth**.

Forced provider failure recovery:

```text
PHASE_A3_FAILURE_RECOVERY PASS forced_provider_failure=1 device_mic=1 opus=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

Mid-playback cancellation/barge-in:

```text
PHASE_A3_CANCEL_LIVE PASS async_lane=1 preemptive_cancel=1 playback_cancel=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

Final physical self-initiation / touch sign-off:

```text
PHASE_A3_SELF_INIT PROVIDERS PASS transcript_chars=40 reply_chars=109 pcm_bytes=258048
PHASE_A3_SELF_INIT TURN1 PASS touch_start=1 stt=1 thinker=1 tts=1 device_speaker=1
PHASE_A3_SELF_INIT PASS touch_start=1 device_event=1 real_roundtrip=1 stt=1 thinker=1 tts=1 touch_cancel=1 playback_cancel=1 correlated_control=1 torque_released=1 body_recovery=1 control_lane=usable
```

That final proof establishes:

- physical touch initiates a device-originated `voice.request` event;
- host queues/ACKs the versioned device event rather than scraping logs;
- real mic -> STT -> Kadence identity/thinker -> TTS -> robot speaker completes;
- touch during active playback locally cancels the device path and informs the host;
- body/control lane is immediately usable afterward;
- torque is released.

**Do not reopen A3 unless a later A4/B regression test provides concrete evidence of a bug.**

---

## 7. Current firmware/runtime architecture details worth preserving

Current firmware entry is Probe21, but Probe21 now contains product-grade Phase A slices rather than being merely a diagnostic probe.

Probe21 properties:

- one USB Serial/JTAG reader;
- one asynchronous voice worker lane;
- touch events originate from the existing presentation touch owner;
- touch bridge never polls I2C itself;
- touch idle -> `voice.request`;
- touch while voice active -> immediate local cancellation + `voice.touch-cancel` event;
- device-originated events use versioned protocol envelopes;
- host event queue is exposed through `RuntimeBody.next_event()`;
- body command path remains authoritative Probe16 movement execution.

Custom CoreS3 16 MB flash layout is active:

```text
factory  4 MiB
ota_0    4 MiB
ota_1    4 MiB
remaining storage/coredump space reserved
```

PSRAM is deliberately enabled and used for staged voice playback. Keep DMA/task stacks and actual codec write buffers in internal RAM.

---

## 8. Credentials / environment

The user has already configured working OpenAI and Gemini API credentials during testing, but they were set only in the active PowerShell environment and disappear after reboot/new terminal.

Never ask the user to paste keys in chat.

Voice preflight:

```powershell
python C:\KadenceX\source\rebuild\tools\phase_a3_voice_preflight.py
```

Expected healthy output:

```text
PHASE_A3_VOICE_PREFLIGHT PASS httpx=1 edge_tts=1 openai_key=1 gemini_key=1 stt=gpt-transcribe thinker=gemini-3.5-flash-lite voice=en-GB-SoniaNeural
```

If credentials are absent after restart, restore them locally/securely before any real provider test.

---

## 9. What is NOT complete

Only these outer families remain:

### A4 — Phase A integrated reveal / sign-off — NEXT

A1, A2 and A3 are individually complete. A4 must prove the **normal integrated Phase A runtime**, not another isolated subsystem script.

A4 acceptance:

- normal startup path;
- boot -> local presence;
- physical touch -> real voice interaction;
- listening/thinking/speaking presentation coordination;
- safe body reaction;
- return to idle/presence;
- physical touch cancellation while active;
- provider failure degrades/recover cleanly;
- restart/reconnect still works;
- no test/probe UX visible in normal operation;
- no checkpoint-only harness required for ordinary use.

**Phase A completion means:** Kadence looks, behaves and sounds like a companion even before tools are added.

### Phase B — Tools, Memory, Integrations, Companion/Home-Assistant Capabilities — NOT STARTED

Do not start Phase B until A4 signs off unless A4 itself requires a tiny runtime abstraction needed for future tools.

Suggested B family:

- **B1 Tool boundary:** concrete allowlisted ToolBridge, structured success/error, timeout/cancel, no presence/body wedging.
- **B2 Useful tools:** reminders/tasks, time/date/weather-style providers, notes/memory retrieval, local/home actions and explicitly authorised connected services.
- **B3 Durable context/integrations:** inspectable memory/context, home-assistant/orchestration provider, graceful degradation.
- **B4 Daily-use sign-off:** cold boot, presence, voice, tool calls, forced failure, reconnect, restart, runbook.

---

## 10. Implementation discipline from here

- Work in vertical slices that produce something the user can actually see/hear/use.
- Run static/host gates before flashing.
- Flash only when firmware changed.
- Preserve CP19–23 body/serial invariants.
- Preserve A1–A3 signed-off behaviour unless a regression proves a change is necessary.
- Keep `RuntimeBody` / `HostServer` as runtime/control authority.
- Build a **normal daily runtime entry point** around reusable modules. Checkpoint scripts are tests, not the product.
- Keep debugging telemetry available but out of normal presentation.
- A4 should consolidate, not invent another parallel architecture.

---

## 11. Immediate next move in a fresh chat

**Start A4. Do not reopen CP19–23 or A1–A3.**

First inspect the current host/runtime entry points and determine the shortest route from the individually proven Phase A pieces to a single normal runtime that:

1. opens `RuntimeBody`;
2. listens for device-originated `voice.request` / `voice.touch-cancel` events;
3. owns the LAN voice server/provider loop;
4. coordinates the existing presentation/body state path;
5. remains alive across multiple turns;
6. reconnects/degrades cleanly;
7. shuts down cleanly.

Likely files to inspect first:

```text
rebuild/backend/kcore/runtime.py
rebuild/backend/kcore/host.py
rebuild/backend/kcore/serial_transport.py
rebuild/backend/kcore/voice_wire.py
rebuild/backend/kcore/voice_runtime.py
rebuild/firmware/main/probe21.cpp
rebuild/docs/ARCHITECTURE.md
```

Create the smallest normal-runtime entry point possible from the proven modules. Add an A4 gate/live sign-off only as validation; do not make the test harness the product.

---

## 12. Fresh-chat restart prompt

The user can say:

> Read `rebuild/docs/KADENCE_HANDOVER.md` from my `neoncrucible/StackChanSource` repo on branch `kadence/rebuild-kade`, then continue the Kadence rebuild from the documented next step. You lead; batch safe commands where sensible.

That should restore the project context.

---

## 13. Final reminder to future Kade

The difficult runtime, movement, presentation, presence and voice foundations are now real and physically proven.

The next job is **integration, not another subsystem invention**.

A4 should make the existing pieces feel like one companion. After that, Phase B makes her useful.