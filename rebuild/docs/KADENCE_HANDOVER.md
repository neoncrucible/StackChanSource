# Kadence blind rebuild — authoritative restart-safe handover

**Repo:** `neoncrucible/StackChanSource`  
**Branch:** `kadence/rebuild-kade`  
**User workspace:** `C:\KadenceX\source`  
**Firmware workspace:** `C:\KadenceX\source\rebuild\firmware`  
**Hardware:** M5Stack StackChan / CoreS3 / K151, ESP32-S3  
**Normal serial:** `COM4` @ `115200`  
**ESP-IDF:** 5.5.4  
**State date:** 8 Sep 2026
**Phase A starting anchor for RC1:** `70e7d80baa81ef3b280e96e0f3de25e0c52618ed`
**Approved build:** RC1, host 0.2.0 / firmware 0.20.1, source `997654857c3dd6aa2f78c92501c2eda2bf6744fe`; owner-approved on 7 Sep 2026.
**Current authority:** Boss approved the first next-release bundle, excluded Quiz Night and explicitly added dated natural-language reminders. Implement that scope; later face-tracking/enrollment qualification remains separate.
**Current candidate:** RC2, host 0.3.0 / firmware 0.21.0. The implemented approved scope, ownership details, automated checks and physical acceptance procedure are in [RC2_ENGINEERING.md](RC2_ENGINEERING.md). Match source with the package `RELEASE.json`. New hardware features are not yet owner-signed-off.
**Operator manual:** [USER_MANUAL.md](USER_MANUAL.md)

**Acceptance:** [RC1_ACCEPTANCE.md](RC1_ACCEPTANCE.md)

**Next-release review:** [NEXT_RELEASE_PROPOSAL.md](NEXT_RELEASE_PROPOSAL.md) — first bundle approved; quiz excluded.

> **This file is the authoritative continuation document.** In a fresh chat, read this file before proposing work. Do not ask the user to reconstruct prior context unless this document and the referenced repo files are demonstrably insufficient.

---

# 0. CRITICAL: CURRENT AUTHORISATION AND NO-SPOILERS PROTOCOL

Kadence remains Kade's surprise build, with a specific owner-directed transition
on 7 September 2026. The latest owner instruction supersedes earlier broad
implementation freedom for the next release:

- Boss explicitly approved the current RC1 build after a completed physical voice
  turn and clean shutdown. Record that approval; do not ask for it again.
- Boss requested an instruction manual covering **all current features**. Those
  implemented features may be fully documented and explained.
- Boss requested feedback on a Windows server UI, practical/fun utilities, top
  LEDs, top-touch volume and camera capabilities. Those proposals may be discussed.
- **Boss has now signed off the first bundle**, excluding Quiz Night and adding
  natural dated reminders. Proceed with that implementation. Continuous tracking
  and enrolled-person recognition remain behind the documented camera review.
- Keep unrelated unrevealed features, personality details and surprises private.
- Once a scope is approved, lead its implementation autonomously, batch safe work
  and request only the physical observations needed to validate it.
- Never copy credentials from operator messages into files, commits or logs.

The [operator manual](USER_MANUAL.md) is the user-facing guide. The historical
engineering and branch audit records remain available for implementation lessons.

---

# 1. Product definition

Kadence is an **embodied companion and home assistant**, not merely an ESP32 front-end to a chatbot.

Core ownership split:

- **Device:** physical I/O, local safety, immediate feedback, display/avatar/presence, touch ownership, audio hardware ownership and safe body execution.
- **Host:** cognition, identity/persona orchestration, memory, tools, integrations and external providers.
- **Boundary:** device and host communicate through a versioned protocol. Do not bypass it for product behaviour.

Finished Kadence should feel present even when no prompt is active and should remain useful if any one external provider is unavailable.

---

# 2. Non-negotiable architecture contract

`rebuild/docs/ARCHITECTURE.md` is authoritative and currently states:

1. Device owns physical I/O, local safety and immediate feedback.
2. Host owns cognition, memory, orchestration and integrations.
3. Device and host communicate only through a versioned protocol boundary.
4. STT, reasoning, TTS and tool bridges are replaceable providers.
5. Identity/presentation is independent of model provider.
6. Loss of an external integration must not prevent basic device operation.
7. Startup exposes deterministic health states and diagnostics.
8. Long-running operations are cancellable and do not block presence updates.

Additional invariants proven during the rebuild:

- One physical movement lane at a time.
- Movement success ACK only after safe execution **and torque release**.
- Stored zero calibration remains preserved.
- Late ACKs after timeout/cancel cannot poison a healthy session.
- Correlation IDs never cross command lifecycles.
- Malformed/noisy serial traffic must not wedge the host session.
- Reconnect clears stale pending/retired state and releases ownership.
- Do not introduce a duplicate movement implementation.
- Do not introduce a second serial reader/owner.
- Do not introduce a second touch/I2C owner.
- Do not introduce a second I2S/audio owner.
- COM4 is the **control plane only**; voice audio uses LAN/TCP.
- Wi-Fi credentials are RAM-only on the device.
- API keys must never be committed or pasted into chat.

`RuntimeBody` / `HostServer` remain the normal body/control authority.

---

# 3. User workflow / operating rules

During Kadence technical work:

- Address the user as **Boss**.
- Kade leads and writes/commits code within the owner-approved scope.
- Do not ask the user to edit code unless genuinely unavoidable.
- The user explicitly approved **batched safe sequential commands** with fail-fast guards.
- Keep commands compact and PowerShell-compatible.
- Pull/fetch the real remote branch before meaningful local tests. A stale-remote incident previously wasted most of a day.
- Avoid unnecessary `fullclean` / build / flash loops.
- Flash only when firmware changed.
- Do not reflexively delete generated/untracked firmware files.
- If our code is wrong, own it and fix the repo rather than making the user patch it manually.
- Never ask the user to paste API keys or Wi-Fi passwords into chat.

Fresh PowerShell after reboot/new terminal:

```powershell
. C:\Espressif\frameworks\esp-idf-v5.5.4\export.ps1
```

Normal firmware build/flash only when required:

```powershell
cd C:\KadenceX\source\rebuild\firmware
idf.py build
idf.py -p COM4 flash
```

Known generated/untracked local paths may include:

```text
rebuild/backend/kcore/__pycache__/
rebuild/firmware/build/
rebuild/firmware/dependencies.lock
rebuild/firmware/managed_components/
rebuild/firmware/sdkconfig
rebuild/tests/__pycache__/
rebuild/tools/__pycache__/
```

Do not delete them casually.

---

# 4. CURRENT STATE IN ONE SENTENCE

**Runtime/body foundation, Phase A and the current RC1 build are owner-approved. RC1 adds the Phase B host boundary and useful capabilities to normal voice, with the approved avatar and solid terminal presentation. The 9976548 physical run completed voice, body reaction, idle return and clean shutdown. The first next-release bundle is approved, with Quiz Night excluded and natural dated reminders explicitly added. Do not restart B1 or replay Phase A.**

Do not reopen CP19–23 or A1–A4 without concrete regression evidence.

---

# 5. Runtime/body foundation — COMPLETE, DO NOT REOPEN

Checkpoint work through CP23 physically established:

- versioned v1 protocol envelopes and correlation IDs;
- bounded `body.pose` decoding;
- real physical movement through the proven motor path;
- calibration preservation;
- torque release after motion;
- ACK only after physical completion;
- host pending-request lifecycle;
- timeout/cancel retirement and late-ACK hardening;
- presence/heartbeat not blocked by body commands;
- single-owner movement lock;
- real USB Serial/JTAG control over COM4;
- HostServer -> COM4 -> firmware -> motor -> correlated ACK;
- disconnect/reconnect recovery;
- malformed/noisy serial resilience;
- clean runtime ownership and shutdown.

Final foundation proof:

```text
CP23_LIVE PASS runtime_owner=1 sequential_commands=1 correlated=1 torque_released=1 clean_path=1
```

Current host authority:

```text
rebuild/backend/kcore/host.py
rebuild/backend/kcore/serial_transport.py
rebuild/backend/kcore/runtime.py
```

Do not create CP24-style infrastructure work just to keep checkpoint numbering alive.

---

# 6. PHASE A — COMPLETE AND SIGNED OFF

Phase A transformed the proven chassis/runtime into the embodied Kadence interaction layer. All Phase A slices are complete.

## A1 — Display architecture + visual identity — COMPLETE

Primary module:

```text
rebuild/firmware/main/presentation.cpp
```

Established:

- intentional product presentation replacing the old purple/probe UX;
- explicit product states including boot/idle/attentive/listening/thinking/speaking/tool/offline/degraded/fault/recovery;
- purposeful touch behaviour;
- rendering owned locally by the device and independent of host/model latency;
- diagnostics retained without becoming the normal UX.

Do not spoil unrevealed visual details in conversation.

## A2 — Local presence / embodied behaviour — COMPLETE

Primary module:

```text
rebuild/firmware/main/presence_engine.cpp
```

Established:

- local autonomous idle presence;
- interaction immediately pre-empts/yields presence;
- presence remains responsive during host delay;
- safe movement ownership and torque policy remain intact.

Final A2 proof:

```text
PHASE_A2_LIVE PASS precondition=1 interrupt=1 command=1 correlated=1 torque_released=1 recovery=1
```

## A3 — Voice + identity/personality interaction loop — COMPLETE

Current live provider stack:

- OpenAI STT: `gpt-transcribe`
- Gemini thinker: `gemini-3.5-flash-lite`
- Edge TTS: `en-GB-SoniaNeural`
- Kadence identity/persona wrapper independent of provider

Current data/control architecture:

- COM4 remains control-only.
- Voice audio is LAN/TCP.
- Device uplink: 16 kHz mono, 60 ms Opus frames.
- Host wraps raw Opus into Ogg Opus for OpenAI transcription.
- Gemini provides the reasoning reply through the Kadence identity layer.
- Edge Sonia TTS returns MP3.
- `miniaudio` decodes/resamples to 16 kHz mono PCM.
- Reply PCM is staged in CoreS3 PSRAM.
- Actual codec/I2S writes copy through internal RAM DMA-safe scratch before playback.
- Voice work runs on an asynchronous device worker lane.
- Touch during an active voice turn can cancel blocked LAN I/O and local staged playback.
- No duplicate I2S/I2C/touch/serial owner.

Important firmware modules:

```text
rebuild/firmware/main/voice_lan.cpp
rebuild/firmware/main/voice_cancel_io.cpp
rebuild/firmware/main/voice_playback_buffer.cpp
rebuild/firmware/main/voice_turn_lane.cpp
rebuild/firmware/main/touch_voice_bridge.cpp
rebuild/firmware/main/probe21.cpp
```

Important host modules:

```text
rebuild/backend/kcore/identity.py
rebuild/backend/kcore/voice_providers.py
rebuild/backend/kcore/voice_wire.py
rebuild/backend/kcore/serial_transport.py
rebuild/backend/kcore/runtime.py
rebuild/backend/kcore/host.py
```

Key live proofs:

```text
PHASE_A3_ROUNDTRIP PASS stt=1 thinker=1 tts=1 device_mic=1 opus=1 device_speaker=1 correlated=1 body_command=1 torque_released=1 recovery=1
```

User explicitly reported playback **smooth** after the PSRAM/DMA-safe playback fix.

```text
PHASE_A3_FAILURE_RECOVERY PASS forced_provider_failure=1 device_mic=1 opus=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

```text
PHASE_A3_CANCEL_LIVE PASS async_lane=1 preemptive_cancel=1 playback_cancel=1 correlated=1 torque_released=1 body_recovery=1 control_lane=usable
```

```text
PHASE_A3_SELF_INIT PASS touch_start=1 device_event=1 real_roundtrip=1 stt=1 thinker=1 tts=1 touch_cancel=1 playback_cancel=1 correlated_control=1 torque_released=1 body_recovery=1 control_lane=usable
```

A3 is signed off. Do not reopen it without a regression.

## A4 — Integrated normal Phase A runtime — COMPLETE

Normal product entry point:

```powershell
kadence
```

Implementation:

```text
rebuild/backend/kcore/appliance.py
rebuild/pyproject.toml
```

The normal runtime now:

- owns one LAN voice server;
- opens `RuntimeBody` as the single control owner;
- consumes device-originated `voice.request` events;
- consumes device-originated `voice.touch-cancel` events;
- supports repeated touch-initiated turns without restarting;
- runs the real provider pipeline;
- cancels active provider work when required;
- sends the existing safe post-turn body reaction through `body.pose`;
- leaves local presence device-owned;
- supervises COM4 disconnects;
- automatically reconnects after device reset/restart;
- shuts down cleanly;
- does not import A3 test harnesses.

A4 static proof:

```text
PHASE_A4_GATE PASS normal_entry=1 runtime_owner=1 device_events=1 repeated_turns=1 touch_cancel=1 provider_cancel=1 body_reaction=1 reconnect=1 clean_shutdown=1 single_voice_server=1 no_test_harness=1
```

A normal no-speech turn is also productized: an empty STT result is represented explicitly as `VoiceNoSpeechDetected`, which produces a short spoken retry response instead of cascading into a provider/device proof failure.

Final A4 live sequence proved all of the following inside the ordinary `kadence` process:

1. startup into device-owned local presence;
2. repeated touch-initiated conversations;
3. no-speech spoken recovery;
4. normal real STT -> thinker -> TTS conversation;
5. safe body reaction;
6. return to idle;
7. physical CoreS3 reset while host remained running;
8. automatic reconnect without restarting `kadence`;
9. another complete conversation after reconnect.

Final observed proof included:

```text
KADENCE_RUNTIME RECONNECT delay_s=2.0
KADENCE_RUNTIME DEVICE ready presence=local
KADENCE_RUNTIME TURN start trigger=touch
KADENCE_RUNTIME PROVIDERS complete transcript_chars=61 reply_chars=399 pcm_bytes=755712
KADENCE_RUNTIME TURN complete seq=3 voice=1 body_reaction=1 idle_return=1
```

**A4 PASS. PHASE A COMPLETE.**

Do not tell the user what unrevealed presentation/personality details were intended. The completed experience remains part of the surprise build.

---

# 7. Current normal runtime / daily test path

When provider credentials are available in the current PowerShell environment, ordinary runtime startup is simply:

```powershell
kadence
```

Typical healthy startup:

```text
KADENCE_RUNTIME READY port=COM4 lan=<host-ip>:<port> touch_start=1 touch_cancel=1 reconnect=1
KADENCE_RUNTIME DEVICE ready presence=local
```

A healthy normal turn ends with:

```text
KADENCE_RUNTIME PROVIDERS complete ...
KADENCE_RUNTIME TURN complete seq=<n> voice=1 body_reaction=1 idle_return=1
```

Voice preflight remains available:

```powershell
python C:\KadenceX\source\rebuild\tools\phase_a3_voice_preflight.py
```

Expected healthy output:

```text
PHASE_A3_VOICE_PREFLIGHT PASS httpx=1 edge_tts=1 openai_key=1 gemini_key=1 stt=gpt-transcribe thinker=gemini-3.5-flash-lite voice=en-GB-SoniaNeural
```

Credentials are supplied by process environment or local prompts. Prompted secrets are process-only in the CLI. The RC2 desktop offers optional Windows Credential Manager storage. Use `python -m kcore.appliance --visible-input` for the owner-approved visible local entry, or omit the flag to hide it.

Never place secrets in repo code, documentation, logs or chat.

---

# 8. Current firmware architecture worth preserving

The selected firmware entry remains `rebuild/firmware/main/probe21.cpp` for historical reasons, but it now composes product-grade Phase A modules rather than being merely a simple diagnostic probe.

Probe21 currently preserves:

- one USB Serial/JTAG reader;
- one asynchronous voice worker;
- one touch/I2C owner in presentation;
- atomic touch action publication;
- idle touch -> versioned `voice.request` event;
- active touch -> immediate local cancellation + versioned `voice.touch-cancel` event;
- device-originated events queued by host rather than log-scraped;
- body execution delegated to the already-proven Probe16 path;
- local presence task independent of host/provider work.

Do not rename or restructure this just for aesthetics unless there is a real product/maintenance reason. Stability matters more than eliminating the word `probe` from a filename.

---

# 9. Flash / memory layout

The CoreS3 16 MB custom partition layout is active and intentionally leaves room for future OTA/product storage:

```text
factory  4 MiB
ota_0    4 MiB
ota_1    4 MiB
remaining flash reserved for storage/coredump
```

Relevant files:

```text
rebuild/firmware/partitions.csv
rebuild/firmware/sdkconfig.defaults
rebuild/firmware/CMakeLists.txt
```

PSRAM is enabled for staged voice playback.

Important rule:

- PSRAM is storage/jitter buffering only.
- Actual codec/I2S playback drains through internal RAM DMA-safe scratch.

The previous speaker stutter was fixed by demand-growing PSRAM staging plus internal DMA-safe playback copying. Do not regress to direct network-fed playback or direct codec writes from PSRAM.

---

# 10. Key gates / diagnostic references

These are validation tools, not the product runtime:

```text
rebuild/tools/checkpoint23_gate.py
rebuild/tools/checkpoint23_live.py
rebuild/tools/phase_a1_gate.py
rebuild/tools/phase_a2_gate.py
rebuild/tools/phase_a2_live.py
rebuild/tools/phase_a3_gate.py
rebuild/tools/phase_a3_bridge_gate.py
rebuild/tools/phase_a3_voice_gate.py
rebuild/tools/phase_a3_voice_preflight.py
rebuild/tools/phase_a3_voice_wire_gate.py
rebuild/tools/phase_a3_device_audio_gate.py
rebuild/tools/phase_a3_device_audio_live.py
rebuild/tools/phase_a3_roundtrip_live.py
rebuild/tools/phase_a3_failure_recovery_live.py
rebuild/tools/phase_a3_cancel_gate.py
rebuild/tools/phase_a3_cancel_live.py
rebuild/tools/phase_a3_self_init_gate.py
rebuild/tools/phase_a3_self_init_live.py
rebuild/tools/phase_a4_gate.py
```

Do not make checkpoint scripts the normal user journey.

---

# 11. Useful commit anchors

These are useful historical anchors if debugging requires archaeology. Do not replay them as a to-do list.

- `c5e418e67f208a3e4e331d0a91a7571ba955e866` — staged playback gate requiring DMA-safe scratch.
- `b26f556c17794cc14e6c5ee9f4b09e12844e1079` — demand-grown PSRAM + internal DMA-safe playback fix.
- `7a0b1ebcf67bd669e8837ad29a7112b700b7972e` — final A3 self-init integration state before physical sign-off.
- `60ce1b6687c06e45d1090a343ebf6110760a6e2b` — handover corrected after A3 sign-off.
- `1f9083f15717eb7aa62026b1009a18bcec862734` — initial normal appliance runtime.
- `b60d4b0cfcc75bd1583b816df0cf404b365d82c7` — `kadence` console entry point.
- `29c3cd0c6cc433908a3f4da8db5f9431a85153fa` — A4 static gate.
- `509ff8b85147fae31b073c8e6812841f7e1c2e8c` / `816b48e88901c19205b3268171339d6b7f814430` — explicit no-speech recovery path.
- `e3827f8f69b193bcb65080a66b87177d4563c84f` — A4 gate updated to require no-speech recovery.
- `36850a0b46b81cc45707f2ff5abbe4f9f3c8bc1e` — handover state immediately before final Phase A reconnect proof was recorded here.

Use `git log` / GitHub history if finer-grained archaeology is needed.

---

# 12. Known current constraints / technical debt

These are not Phase A failures, but future work should know they exist:

- Normal conversation starts from front-screen touch. RC2 adds the approved host reminder notification path; older branches do not authorise other initiation modes.
- Current capture window is turn-based/fixed-duration (normal default 4.8 s). Do not casually replace it without preserving cancellation and device/host ownership.
- CLI credentials come from environment/prompts. The RC2 desktop supports session-only fields and optional Windows Credential Manager; ordinary JSON never stores secrets.
- Wi-Fi password is currently requested locally when needed; firmware stores Wi-Fi credentials in RAM only.
- LAN host selection can be affected by VPN/multiple adapters; `KADENCE_LAN_HOST` exists as an override.
- The product runtime currently depends on external OpenAI/Gemini/Edge providers for full cognition/voice, while local presence and physical safety remain independent.
- OTA partitions exist, but normal OTA product delivery is not yet the user workflow.
- Current firmware entry naming still says Probe21; this is acceptable until a product reason justifies changing it.

Do not turn technical debt cleanup into a sprawling infrastructure phase. Fix debt when it blocks a real product goal or causes a regression.

---

# 13. PHASE B — RC1 IMPLEMENTED AND OWNER-APPROVED

Phase B is the second and final outer build family: **tools, useful context/memory, integrations and companion/home-assistant capability**.

Current capabilities are documented in `USER_MANUAL.md` at the owner's request. Discuss the explicitly requested next-release proposal; preserve unrelated surprises.

## B1 — Safe host-side tool boundary — IMPLEMENTED / HOST VERIFIED

The provider protocol already exists in:

```text
rebuild/backend/kcore/providers.py
```

Current interface:

```python
class ToolBridge(Protocol):
    async def invoke(self, name: str, arguments: dict) -> dict: ...
```

RC1 implements this interface in `rebuild/backend/kcore/tool_bridge.py`. The strict schema validator carries forward the proven Alpha 2 implementation, with deadline, cancellation, result-limit and confirmation hardening. Read `RC1_ENGINEERING.md` and `BRANCH_AUDIT.md` before changing the accepted baseline. The requirements below remain acceptance invariants, not a new to-do list.

Required properties:

- explicit allowlisted tool registry;
- structured tool schemas / validated arguments;
- structured success/error result envelope;
- per-tool timeout;
- cancellation propagation;
- unknown/denied tool handling;
- a hanging/broken tool must not wedge voice, presence, serial or body ownership;
- tool execution remains **host-side**;
- model/tool output must never gain direct motor/touch/audio hardware authority;
- distinguish normal reasoning from tool-working presentation state through the existing presentation protocol, without duplicating the state system;
- integration failure must return the normal runtime to a healthy conversational state.

B1 was verified host-first. RC1's visual upgrade and authenticated KDV2 uplink were delivered in the accepted matching host/firmware pair. The 9976548 update is now flashed and approved; documentation publication does not require another flash.

Inspect these before implementing:

```text
rebuild/backend/kcore/providers.py
rebuild/backend/kcore/interaction.py
rebuild/backend/kcore/identity.py
rebuild/backend/kcore/appliance.py
rebuild/backend/kcore/runtime_bridge.py
rebuild/backend/kcore/host.py
rebuild/docs/ARCHITECTURE.md
```

Boss approved the first RC2 bundle, excluded Quiz Night and added dated reminders. That scope is implemented. Continuous tracking/enrollment and account-specific Home Assistant actions retain the documented later boundary.

## B2 / B3 / B4 — accepted release scope

RC1 includes explicit saved notes, local to-do items, a clock, arithmetic, weather,
optional read-only Home Assistant status and bounded completed-turn context. The
ordinary appliance owns the implementation and does not import diagnostic harnesses.
See `USER_MANUAL.md` for all current capabilities and operating instructions.

Boss approved this release after the observed 9976548 run. `RC1_ACCEPTANCE.md`
records the actual evidence. Do not invent per-feature physical observations:
the latest log covers one complete ordinary voice turn and shutdown. Earlier
Phase A live proofs and current automated tests retain their own scope.

Subsequent regression work should cover cold start, normal/repeated conversation,
tools and confirmation, cancellation, provider/integration failure, reconnect,
return to normal interaction and restart. These scenarios protect future work;
they are not a reason to withhold or reopen the owner's recorded RC1 approval.

---

# 14. EXACT NEXT MOVE IN A FRESH CHAT

**Continue RC2 qualification/delivery; do not rebuild completed Phase A or ask for scope approval again.**

1. Read `RC2_ENGINEERING.md`, `USER_MANUAL.md` and the current package identity.
   RC2 implements the approved Windows console, reminders/focus, workbench,
   snapshots/QR/Gemini descriptions, LEDs, touch volume and LED Memory. Quiz is out.
2. Fetch the actual `kadence/rebuild-kade` branch. Inspect the current Actions run
   before changing code. The `windows-desktop` job depends on host and firmware
   success and runs the actual frozen worker before publishing one combined ZIP.
   If a job fails, resolve its concrete evidence and rerun/build a fresh matched
   commit. Never deliver a package from a different source commit.
3. Deliver the complete `Kadence-RC2-<12-character-commit>.zip`. Extract all files;
   `Flash-Kadence.ps1 -Port COM4` checks desktop/firmware identity and invokes the
   preserved calibration-safe flash helper. Everyday startup is `Kadence.exe`.
   No daily ESP-IDF/Python environment is required by the executable.
4. Perform the short owner hardware procedure in `RC2_ENGINEERING.md`: normal
   voice/strips, top volume/mute, timed reminders, LED Memory, repeated deliberate
   camera captures and cancellation, then stop/restart/reconnect. Automated tests
   cannot supply those physical observations. Retain RC1 `9976548` as rollback.
5. Record actual RC2 observations and owner approval when supplied. Do not mark
   new hardware signed off on the strength of the earlier RC1 voice log.
6. Face tracking/enrolled-person recognition follow measured camera qualification;
   do not enable them or invent recognition proof in this release. Home Assistant
   device actions need the owner's actual entity/action scope.
7. Keep credentials and image/QR/conversation contents out of commits and diagnostic
   exports. Preserve unrelated surprises and all existing hardware owners.

---

# 15. Fresh-chat restart prompt

The user can start a new chat with exactly this:

> Read `rebuild/docs/KADENCE_HANDOVER.md` from my `neoncrucible/StackChanSource` repo on branch `kadence/rebuild-kade`. RC1 is approved and the first RC2 bundle is implemented. Continue from its current CI/package and hardware qualification state; the quiz is excluded and dated reminders are included. Preserve unrelated surprises and batch safe commands where sensible.

That should be sufficient to restore the project without the user repeating history.

---

# 16. Final instruction to future Kade

The hard foundation and the entire Phase A embodied interaction stack are already real and live-proven.

The user requested and has now approved a substantial integrated RC1 build, including the avatar/UI. Preserve that accepted baseline. Prepare coherent next-release work within the scope Boss approves; do not return to tiny unconnected checkpoint delivery.

Do not make the user spend another day admiring infrastructure for its own sake.

Build and qualify the approved scope **behind the proven boundaries**, preserve unrelated surprises and test vertically. Do not ask again for already recorded approval.

## Latest owner scope decision

Boss: drop the quiz game; approve the rest of the first bundle; add date-aware
“remind me at…” and “tomorrow remind me I need to…” requests. This explicit
approval supersedes earlier awaiting-approval statements for the first bundle.
Do not request that approval again. Keep the approved 9976548 firmware as the
physical rollback baseline while building and verifying its successor.
