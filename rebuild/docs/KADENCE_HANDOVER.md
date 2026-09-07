# Kadence blind rebuild — restart-safe handover

**Repo:** `neoncrucible/StackChanSource`  
**Branch:** `kadence/rebuild-kade`  
**Workspace:** `C:\KadenceX\source`  
**Firmware:** `C:\KadenceX\source\rebuild\firmware`  
**Hardware:** M5Stack StackChan / CoreS3 / K151, ESP32-S3  
**Normal serial:** COM4 @ 115200  
**ESP-IDF:** 5.5.4

> This is the authoritative restart document. Read it before continuing. Preserve the blind/no-spoilers spirit for unfinished areas. Kade leads architecture/code; the user performs physical QA. Batch safe sequential commands where sensible.

---

## 1. Product definition

Kadence is an **embodied companion and home assistant**, not just an ESP32 chatbot front-end.

- Device owns physical I/O, local safety, immediate feedback and embodied presentation.
- Host owns cognition, memory, orchestration and integrations.
- Device/host communication crosses a versioned protocol boundary only.
- STT / Thinker / TTS / ToolBridge remain replaceable.
- Identity stays Kadence regardless of model provider.

Finished Kadence means intentional visual identity, local presence, natural voice interaction, safe embodied reactions, controlled tools/integrations, durable useful context where appropriate, graceful recovery, and a normal daily-use runtime.

---

## 2. Non-negotiable invariants

`rebuild/docs/ARCHITECTURE.md` remains authoritative.

Preserve:

- one physical movement lane at a time;
- movement success ACK only after safe execution and torque release;
- late ACKs after timeout/cancel cannot poison a healthy session;
- correlation IDs never cross command lifecycles;
- malformed/noisy serial must not wedge the host;
- reconnect clears stale ownership/pending state;
- long operations are cancellable and do not block local presence;
- no duplicate movement, serial, touch, I2S or I2C owners;
- COM4 is control-only; audio data plane is LAN/TCP;
- Wi-Fi credentials are RAM-only on device;
- API keys never go in chat or source.

`RuntimeBody` / `HostServer` remain the normal body/control authority.

---

## 3. User workflow

- Address user as **Boss** during Kadence work.
- Keep instructions compact/direct.
- Kade writes/commits code; do not ask user to edit code unless unavoidable.
- Pull current branch before meaningful local tests.
- Avoid redundant clean/build/flash loops.
- Flash only when firmware changed.
- Do not casually delete generated/untracked firmware paths.
- User explicitly approved **batched safe commands** with fail-fast guards.

Fresh PowerShell ESP-IDF activation:

```powershell
. C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1
```

Build/flash only when needed:

```powershell
cd C:\KadenceX\source\rebuild\firmware
idf.py build
idf.py -p COM4 flash
```

Voice provider credentials are environment-only and disappear after a new terminal/reboot unless the user deliberately persists them later.

---

## 4. Runtime/body foundation — COMPLETE, DO NOT REOPEN

CP19–CP23 physically proved:

- real USB Serial/JTAG COM4 transport;
- HostServer -> firmware -> motor -> correlated ACK;
- safe bounded body movement;
- torque release;
- calibration preservation;
- timeout/cancel retirement + late-ACK hardening;
- malformed traffic resilience;
- reconnect recovery;
- single runtime owner;
- clean shutdown.

Final foundation proof:

```text
CP23_LIVE PASS runtime_owner=1 sequential_commands=1 correlated=1 torque_released=1 clean_path=1
```

Do not create CP24-style infrastructure work unless a real regression requires it.

---

## 5. Phase A status

# A1 — Display architecture + visual identity — COMPLETE

Current product presentation lives in `rebuild/firmware/main/presentation.cpp` with intentional boot/idle/attentive/listening/thinking/speaking/tool/offline/degraded/fault/recovery states and purposeful touch behaviour.

The old purple/probe display is not the normal UX. Do not regress to probe scaffolding.

# A2 — Presence engine + embodied behaviour — COMPLETE

`rebuild/firmware/main/presence_engine.cpp` provides local autonomous idle presence independent of host latency. Interaction pre-empts/yields presence safely.

Final proof:

```text
PHASE_A2_LIVE PASS precondition=1 interrupt=1 command=1 correlated=1 torque_released=1 recovery=1
```

# A3 — Voice + personality loop — COMPLETE AND SIGNED OFF

Live stack:

- OpenAI STT: `gpt-transcribe`
- Gemini thinker: `gemini-3.5-flash-lite`
- Edge TTS: `en-GB-SoniaNeural`
- provider-independent Kadence identity
- device mic -> 16 kHz mono 60 ms Opus -> LAN/TCP -> host
- host wraps Opus into Ogg for STT
- Sonia MP3 decoded with `miniaudio` to 16 kHz mono PCM
- reply staged in CoreS3 PSRAM
- actual codec/I2S writes drain through internal DMA-safe RAM
- voice worker is asynchronous and cancellable
- touch while active interrupts blocked LAN I/O and local speaker playback
- no duplicate serial/touch/audio owner

Key modules:

```text
rebuild/firmware/main/voice_lan.cpp
rebuild/firmware/main/voice_cancel_io.cpp
rebuild/firmware/main/voice_playback_buffer.cpp
rebuild/firmware/main/voice_turn_lane.cpp
rebuild/firmware/main/touch_voice_bridge.cpp
rebuild/firmware/main/probe21.cpp
rebuild/backend/kcore/voice_providers.py
rebuild/backend/kcore/voice_wire.py
rebuild/backend/kcore/serial_transport.py
rebuild/backend/kcore/runtime.py
rebuild/backend/kcore/host.py
```

Signed-off proofs:

```text
PHASE_A3_ROUNDTRIP PASS stt=1 thinker=1 tts=1 device_mic=1 opus=1 device_speaker=1 correlated=1 body_command=1 torque_released=1 recovery=1
```

User reported playback **smooth**.

```text
PHASE_A3_FAILURE_RECOVERY PASS forced_provider_failure=1 device_mic=1 opus=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

```text
PHASE_A3_CANCEL_LIVE PASS async_lane=1 preemptive_cancel=1 playback_cancel=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

```text
PHASE_A3_SELF_INIT PASS touch_start=1 device_event=1 real_roundtrip=1 stt=1 thinker=1 tts=1 touch_cancel=1 playback_cancel=1 correlated_control=1 torque_released=1 body_recovery=1 control_lane=usable
```

Do not reopen A3 without concrete regression evidence.

---

## 6. A4 — Integrated Phase A runtime — ACTIVE, NEAR SIGN-OFF

A4 now has a **real normal runtime**, not a checkpoint harness.

Normal entry point:

```powershell
kadence
```

Implementation:

- `rebuild/backend/kcore/appliance.py`
- console script in `rebuild/pyproject.toml`
- one LAN voice server owned by the appliance runtime;
- repeated device-originated `voice.request` turns;
- device-originated `voice.touch-cancel` handling;
- provider cancellation;
- `RuntimeBody` remains control owner;
- safe post-turn body reaction through existing `body.pose` lane;
- local presence remains device-owned;
- COM4 disconnect supervision and reconnect loop;
- clean Ctrl+C shutdown path;
- no A3 test harness imported by product runtime.

A4 static gate:

```text
PHASE_A4_GATE PASS normal_entry=1 runtime_owner=1 device_events=1 repeated_turns=1 touch_cancel=1 provider_cancel=1 body_reaction=1 reconnect=1 clean_shutdown=1 single_voice_server=1 no_test_harness=1
```

### A4 live product proof — 7 Sep 2026

User ran normal `kadence` runtime and completed two consecutive touch-initiated turns without restarting the process:

```text
KADENCE_RUNTIME READY port=COM4 lan=192.168.40.174:63106 touch_start=1 touch_cancel=1 reconnect=1
KADENCE_RUNTIME DEVICE ready presence=local
KADENCE_RUNTIME TURN start trigger=touch
KADENCE_RUNTIME PROVIDERS complete transcript_chars=0 reply_chars=27 pcm_bytes=78336
KADENCE_RUNTIME TURN complete seq=1 voice=1 body_reaction=1 idle_return=1
KADENCE_RUNTIME TURN start trigger=touch
KADENCE_RUNTIME PROVIDERS complete transcript_chars=21 reply_chars=104 pcm_bytes=227328
KADENCE_RUNTIME TURN complete seq=2 voice=1 body_reaction=1 idle_return=1
```

User reported: **“works perfectly.”**

The first turn intentionally proved no-speech handling. Empty OpenAI transcription is now an explicit normal condition (`VoiceNoSpeechDetected`) that produces a short spoken retry prompt and still completes playback/handoff instead of cascading into a provider/device proof failure.

### Remaining A4 sign-off

Only prove the integrated runtime survives a **real device reset/disconnect/reconnect** and then performs another normal touch voice turn, while the product UI returns normally rather than probe scaffolding.

If that passes, mark **Phase A complete** and move to Phase B.

---

## 7. Current firmware details worth preserving

Current firmware entry remains `probe21.cpp`, but Probe21 now composes product-grade Phase A modules rather than acting as a simple diagnostic probe.

Properties:

- one USB Serial/JTAG reader;
- one asynchronous voice worker;
- existing presentation task remains sole touch/I2C owner;
- touch release publishes an atomic action sequence;
- idle touch -> versioned `voice.request` event;
- active touch -> immediate local cancel + versioned `voice.touch-cancel` event;
- host queues device events instead of scraping logs;
- body path reuses proven Probe16 execution;
- presence engine remains local.

Custom CoreS3 16 MB flash layout:

```text
factory  4 MiB
ota_0    4 MiB
ota_1    4 MiB
remaining storage/coredump reserved
```

PSRAM is enabled for staged playback; actual codec DMA writes stay in internal RAM.

---

## 8. Phase B — NOT STARTED

Do not start until A4 reconnect/reset sign-off passes.

Suggested outer slices:

- **B1 Tool boundary:** concrete allowlisted ToolBridge, structured success/error, timeout/cancel, no presence/body wedging.
- **B2 Useful tools:** reminders/tasks, time/date/weather-style providers, notes/memory retrieval, local/home actions and explicitly authorised connected services.
- **B3 Durable context/integrations:** inspectable memory/context, home-assistant/orchestration provider, graceful degradation.
- **B4 Daily-use sign-off:** cold boot, presence, voice, tool calls, forced failure, reconnect, restart, runbook.

Phase B completion means a genuinely useful embodied companion/home assistant, not merely a technically sound platform.

---

## 9. Immediate next move

If the normal `kadence` process is still running, **do not stop it**.

Reset/reboot the CoreS3 once while `kadence` remains running. The host should detect the physical disconnect, enter its reconnect loop, bind COM4 again when the board returns, and print another `KADENCE_RUNTIME DEVICE ready presence=local`.

Then touch Kadence once and complete one normal spoken turn. Confirm:

- product UI returns normally after reset (no purple/probe scaffolding);
- runtime reconnects without manual restart;
- the post-reconnect turn reaches `KADENCE_RUNTIME TURN complete ... idle_return=1`.

If all three hold, sign off A4 / **Phase A complete**, update this handover, and begin Phase B / B1.

---

## 10. Fresh-chat restart prompt

User can say:

> Read `rebuild/docs/KADENCE_HANDOVER.md` from my `neoncrucible/StackChanSource` repo on branch `kadence/rebuild-kade`, then continue the Kadence rebuild from the documented next step. You lead; batch safe commands where sensible.
