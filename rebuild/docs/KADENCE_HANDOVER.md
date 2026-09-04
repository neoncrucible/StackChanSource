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

## 1. What this project actually is

Kadence is intended to be an **embodied companion and home assistant**, not merely an ESP32 front-end to a chatbot.

The device should feel *present* even when it is not actively answering a prompt. The host should own cognition, memory, orchestration and integrations; the ESP32 should own physical I/O, local safety, immediate feedback and the embodied presentation layer.

The user explicitly gave Kade freedom to redesign the project from scratch as a **blind/no-spoilers rebuild**. Kade chooses architecture, avatar, splash, body behaviour, UI and implementation details. During the blind build, the user performs physical/serial QA and pastes outputs, but should not be required to author code.

The blind-build secrecy restriction can now be considered lifted for completed areas because the runtime foundation has already been revealed. However, preserve the spirit of the project: avoid dumping every future surprise before it is implemented unless the user asks.

---

## 2. Definition of “finished Kadence”

Do **not** call the project finished again merely because transport/runtime tests pass.

A finished build should, at minimum, provide:

1. **A real visual identity** on the CoreS3 display — no probe bars, purple test field, touch marker or other scaffolding as the primary experience.
2. **An avatar / face / presentation language** chosen by Kade, with intentional idle, listening, thinking, speaking, tool-use, error/offline and recovery states.
3. **Presence** — subtle autonomous on-device behaviour while idle, not a dead screen waiting for prompts. Presence updates must continue independently of long host operations.
4. **Personality / identity** that is independent of model provider. Kadence should remain Kadence if the reasoning provider changes.
5. **Voice interaction** — wake/listen -> STT -> reasoning/persona -> TTS -> playback, with sensible cancellation and failure behaviour.
6. **Safe embodied reactions** — body movement and display behaviour coordinated with interaction state, using the already-proven body command path and safety contract.
7. **Tools / assistant capabilities** behind a controlled host tool bridge, with timeouts, cancellation, clear failures and no ability for a tool failure to wedge basic presence.
8. **Useful companion/home-assistant behaviour** rather than a demo-only command script.
9. **Recoverability** — serial reconnects, malformed traffic, provider failures and unavailable integrations should degrade cleanly.
10. **A normal runnable entry point** for daily use, not a pile of checkpoint scripts.

The old project had previously proven useful pieces such as wake word `Kadence`, faster-whisper, a British female TTS voice and cloud reasoning. Those are reusable references, **not architectural requirements**. Provider interfaces in the rebuild are intentionally replaceable.

---

## 3. Non-negotiable architecture contract

`rebuild/docs/ARCHITECTURE.md` is authoritative. Preserve these invariants:

1. Device owns physical I/O, local safety and immediate feedback.
2. Host owns cognition, memory, orchestration and integrations.
3. Device and host communicate only through a versioned protocol boundary.
4. STT, reasoning, TTS and tool bridges are replaceable providers.
5. Identity/presentation is independent of model provider.
6. Loss of any external integration must not prevent basic device operation.
7. Startup exposes deterministic health states and diagnostics.
8. Long-running operations are cancellable and do not block presence updates.

Additional implementation rules established during the rebuild:

- One physical body command owns the movement lane at a time.
- Success ACK for physical movement comes **after** safe execution and torque release.
- Late ACKs after timeout/cancel must not poison a healthy session.
- Correlation IDs must never cross command lifecycles.
- Malformed/noisy serial lines must not wedge the host session.
- Reconnect must release stale ownership/pending state.
- Avoid a second movement/protocol implementation when an existing proven path can be reused.

---

## 4. User working style / project operating rules

These matter enough to preserve explicitly.

- User prefers **one command at a time** (“baby steps”).
- Kade leads the design and writes/commits code. Do **not** ask the user to write code unless unavoidable.
- Before local build/test, keep repo state fresh (`git pull --ff-only` / fetch as appropriate). A stale-remote incident previously wasted much of a day.
- Do not casually clean generated/untracked firmware artifacts.
- Avoid redundant fullclean/build/flash loops.
- If a mistake is ours, say so clearly and fix it ourselves.
- Do not imply background/asynchronous work.
- User is happy to QA physical motion, touch, audio and display behaviour.
- Keep technical instructions compact; banter is welcome but not at the expense of precision.
- Do not create endless infrastructure checkpoints. Remaining work is intentionally grouped into only **two checkpoint families** (Phase A and Phase B below).

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

Do not delete them reflexively.

---

## 5. Current real state — what is complete

### 5.1 Runtime/body foundation is complete and live-proven

Checkpoint work through CP23 established and physically verified:

- versioned v1 protocol envelope and correlation IDs;
- safe bounded `body.pose` command decoding;
- physical movement through the proven motor path;
- torque release after movement;
- calibration preservation;
- ACK only after physical completion;
- host pending request lifecycle;
- timeouts/cancellation and retired late-response IDs;
- non-blocking heartbeat/presence behaviour while commands are outstanding;
- single-owner body command lock;
- real USB Serial/JTAG transport over COM4;
- host serial adapter that filters ESP-IDF log noise and accepts only valid protocol envelopes;
- real HostServer -> COM4 -> firmware -> motor -> correlated ACK path;
- disconnect/reconnect recovery;
- malformed traffic resilience;
- clean runtime ownership and shutdown.

### 5.2 Key live sign-offs

CP19 live:

```text
CP19_LIVE device-ready port=COM4
CP19_LIVE sent id=<id> port=COM4
CP19_LIVE PASS correlated=1 executed=1 torque_released=1 transport=COM4
```

CP20 live:

```text
CP20_LIVE host-bound port=COM4
CP20_LIVE PASS host_server=1 serial_bound=1 correlated=1 executed=1 torque_released=1
```

CP21 live:

```text
CP21_LIVE first-bound port=COM4
CP21_LIVE reconnect-bound port=COM4
CP21_LIVE PASS reconnect=1 second_command=1 stale_state=0 ownership_released=1 torque_released=1
```

CP22 live:

```text
CP22_LIVE host-bound port=COM4
CP22_LIVE PASS malformed_rejected=1 session_healthy=1 fresh_command=1 correlated=1 torque_released=1
```

CP23 live:

```text
CP23_LIVE runtime-bound port=COM4
CP23_LIVE PASS runtime_owner=1 sequential_commands=1 correlated=1 torque_released=1 clean_path=1
```

### 5.3 Current host runtime entry point

`rebuild/backend/kcore/runtime.py` now provides `RuntimeBody`, which:

- opens the real serial port;
- owns a `HostServer` + `SerialBodySession`;
- exposes `send_body_pose()`;
- closes cleanly;
- supports async context-manager use.

This is the correct foundation for the daily-use runtime. Extend from here rather than bypassing it with new probe-only paths.

### 5.4 Provider contracts already exist

`rebuild/backend/kcore/providers.py` defines replaceable protocols:

- `SpeechToText.transcribe(...)`
- `Thinker.stream_reply(...)`
- `TextToSpeech.synthesize(...)`
- `ToolBridge.invoke(...)`

These are interfaces, not evidence that the real voice/tool product loop is complete.

---

## 6. Current real state — what is NOT complete

This section exists because the phrase “functionally complete” was used too early after CP23.

### 6.1 Display/UI is still probe scaffolding

The current device display path in `rebuild/firmware/main/main.cpp` is explicitly a hardware probe:

- deterministic colour/test rendering;
- display log marker `DISPLAY_PROBE`;
- touch press/move draws a simple marker;
- body policy describes `display_driver=probe` and `touch_driver=probe`.

Therefore the purple screen / white line seen by the user is **not a hidden final avatar or intentional final UI**.

### 6.2 No finished avatar or presence engine yet

The “presence” concept was intentionally disclosed as a small spoiler: Kadence should feel like she is *there* while idle, with subtle autonomous behaviour that keeps running independently of cognition/network/model latency. The architectural groundwork for this exists; the actual experience does not yet.

### 6.3 Voice/persona interaction loop is not yet integrated in this rebuild

There are provider interfaces, but the rebuild has not yet been signed off as a complete wake/STT/persona/reasoning/TTS/audio loop.

### 6.4 Tools/integrations are not yet productized

`ToolBridge` is only an interface at present. The finished assistant needs controlled, useful capabilities and graceful failure handling.

---

## 7. Important checkpoint / commit history

Do not replay this history unless debugging requires it; this is context, not a to-do list.

### CP11 — safe physical movement baseline

- Fixed verify-transition I2S re-arm to be idempotent.
- Final sign-off included torque released and post-health OK.
- Key fix commit: `99303b9a60f70914269cb877e1792e5541a81f89`
- Embeddability later: `ed5256caece763598c25f36f2ff7e0a66b20cd0f`

### CP12 — protocol request-ID / ACK correlation

- Real protocol correlation around proven safe movement.

### CP13 — host outbound correlated body.pose lifecycle

- Timeout, pending cleanup, disconnect handling, serialized writes.
- Host commit: `dce28ecef92f289ff46e8f3744c41430da6528c7`

### CP14 — late ACK hardening

- Late ACK after timeout/cancel cannot poison healthy session.
- Host commit: `d372d95d68f6a42751bb35bdc8ab7c1fc3027afe`

### CP15 — command does not block presence

- Heartbeat/presence continues while command is outstanding.

### CP16 — real safe physical completion semantics

- ACK only after safe movement completes and torque is released.
- Calibration remains unchanged.
- Firmware commit: `023155467e6120f00df16a25bda324e1dbd3b2ef`
- Embeddability: `6bd97776c6c1c68581f19b74480fbcd11d785d30`

### CP17 — single-owner movement lane

- `_command_lock` owns the whole movement lifecycle.
- Commit: `eaf66c76fa2f9bd1037ae5b15ac38b14df56528b`

### CP18 — host/firmware wire-contract integration

- Simulated actual host/body wire lifecycle around CP16 + CP17 semantics.
- Gate matching fix: `b66900910ff9e3f0219a8370766568e5775d43a2`

### CP19 — real COM4 / USB Serial/JTAG transport

Key issue: generated `sdkconfig` originally kept UART0 primary despite updated defaults. Correct actual config after regeneration:

```text
# CONFIG_ESP_CONSOLE_UART_DEFAULT is not set
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
CONFIG_ESP_CONSOLE_SECONDARY_NONE=y
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED=y
CONFIG_ESP_CONSOLE_UART_NUM=-1
```

USB Serial/JTAG RX uses the IDF 5.5 driver-backed VFS path (`driver/usb_serial_jtag_vfs.h`, `usb_serial_jtag_vfs_use_driver()`).

Important commit: `585df7d0cbe3e7ee8b5bd25bc2e6237f251cfd06`

### CP20 — actual HostServer bound to real serial body

- Added `rebuild/backend/kcore/serial_transport.py`.
- Host protections remain authoritative; serial adapter handles framing/readiness/log filtering only.

### CP21 — reconnect recovery

- Proved release/rebind/fresh command without stale state.

### CP22 — malformed/noisy traffic resilience

- Proved malformed serial input does not wedge healthy session.

### CP23 — normal runtime owner

- Added `rebuild/backend/kcore/runtime.py`.
- Proved sequential real commands and clean shutdown through the runtime owner.

At this point the **runtime/body foundation is signed off**. Do not create CP24 just to keep numbering infrastructure work.

---

## 8. Stale-state incident — never repeat this

On Sep 3 the local branch believed remote tracking was at `62b09ea...` while the actual GitHub branch was already `f1d2afd...`. The project successfully rebuilt/flashed stale CP10 firmware and wasted much of a day.

Rules:

- Anchor all work at `C:\KadenceX\source`.
- Confirm/fetch/pull current `kadence/rebuild-kade` before meaningful local tests.
- Do not infer “latest” from a stale local tracking ref.
- Avoid unnecessary rebuild/flash cycles.

---

## 9. Remaining work — only two checkpoint families

The user explicitly wants to avoid another sprawling sequence. Use these two families as the outer structure. Small corrections remain inside the active family rather than creating new numbered infrastructure checkpoints.

# Phase A — Presence, Identity, UI, Avatar, Voice

**Goal:** transform the proven chassis/runtime into recognisable Kadence.

Suggested internal checkpoints: `A1`–`A4` (flexible; merge steps if possible).

### A1 — Display architecture + final visual identity

- Replace probe display with a real presentation renderer.
- Choose Kade’s own avatar/face/aesthetic and splash/boot presentation.
- Define explicit visual states at minimum: booting, idle, attentive/listening, thinking, speaking, tool-working, offline/degraded, fault/recovery.
- Preserve deterministic hardware diagnostics behind a debug mode/log path; do not throw away useful probes, just remove them as the normal UX.
- Touch should become intentional interaction, not a marker test.
- Keep rendering/device behaviour responsive even if host cognition is slow.

**Acceptance:** device boots into an intentional Kadence UI, touch is purposeful, and the UI does not freeze during a long simulated host operation.

### A2 — Presence engine + embodied behaviour

- Implement a small local presence/state engine on the device.
- Idle should have subtle autonomous behaviour rather than appearing off/dead.
- Presence animation and safe body micro-behaviour must be cancellable/interruptible by interaction.
- Do not spam motors; body motion should feel intentional and respect torque/safety policy.
- Host state changes should map to presentation without tying identity to a specific model provider.

**Acceptance:** leave Kadence idle for several minutes and she continues to feel “there”; start an interaction and presence yields immediately; host delay does not stop local presence updates.

### A3 — Voice + personality loop

- Implement the real interaction orchestrator on the host: listen/wake -> STT -> identity/persona layer -> Thinker -> streamed reply -> TTS -> device audio.
- Provider selection must remain swappable.
- Preserve the established Kadence identity/personality independently of model provider.
- Prefer a natural British female voice; old Edge TTS `en-GB-SoniaNeural` is a previously liked reference, not a mandate.
- Handle cancellation, barge-in where practical, timeout and provider failure.
- Coordinate listening/thinking/speaking states with display and body.

**Acceptance:** user can speak naturally to Kadence and receive a coherent spoken reply while display/body states track the interaction and recover cleanly from a forced provider failure.

### A4 — Phase A integrated reveal / sign-off

- Run the whole normal runtime, not checkpoint-only scripts.
- Verify boot -> presence -> touch/attention -> voice interaction -> body reaction -> return to idle.
- Verify reconnect/restart still works.
- Confirm no probe UI remains in normal operation.

**Phase A completion means:** Kadence looks, behaves and sounds like a companion even before tools are added.

---

# Phase B — Tools, Memory, Integrations, Companion/Home-Assistant Capabilities

**Goal:** make Kadence useful without compromising the embodied experience built in Phase A.

Suggested internal checkpoints: `B1`–`B4` (merge where sensible).

### B1 — Tool execution boundary

- Implement a concrete `ToolBridge` with an allowlisted registry/schema.
- Tool execution remains host-side.
- Enforce timeout/cancellation and structured success/error results.
- A hanging/broken tool must not freeze presence, voice state or body ownership.
- Separate “thinking” from “tool working” presentation state.

**Acceptance:** successful tool call, denied/unknown tool, timeout and cancellation all return the runtime to a healthy conversational state.

### B2 — Core useful companion tools

Prioritise capabilities that match the actual desired product rather than arbitrary demos. Candidate classes:

- reminders/tasks;
- time/date/weather-style information providers;
- notes/memory retrieval;
- local/home-assistant actions;
- connected service actions where available and explicitly authorised.

Keep each integration behind the common ToolBridge rather than baking service-specific logic into personality or device code.

**Acceptance:** at least several genuinely useful commands can be requested conversationally and executed with clear spoken/visual confirmation.

### B3 — Memory / context / home-assistant integration

- Add durable context/memory in a way that is inspectable and does not silently mutate core identity.
- Integrate the chosen home-assistant/orchestration layer (OpenClaw or another provider can be evaluated here; it is not an architectural requirement).
- The project’s long-term direction is companion + home assistant; tool provider choices may evolve.
- Failure or absence of OpenClaw/home services must not prevent basic Kadence operation.

**Acceptance:** useful remembered context survives runtime restart; unavailable home/integration provider degrades gracefully.

### B4 — Final daily-use sign-off

Test the normal user journey, not a synthetic checkpoint sequence:

1. cold boot;
2. local presence without host interaction;
3. voice conversation;
4. body/display response;
5. one or more tool calls;
6. forced tool/provider failure;
7. serial reconnect;
8. clean recovery;
9. clean shutdown/restart.

Create/update a concise runbook for daily startup and troubleshooting.

**Phase B completion means:** the user has a usable embodied Kadence companion/home assistant, not merely a technically sound platform.

---

## 10. Suggested implementation discipline for Phase A/B

- Prefer one **vertical slice** at a time over building every subsystem separately.
- Every checkpoint should end in something the user can actually see/hear/use when possible.
- Run host/static gates before asking for a flash.
- Flash only when firmware changed.
- Preserve proven CP19–23 serial/runtime code unless a failing test provides evidence to change it.
- Keep `RuntimeBody` / `HostServer` as the movement/runtime authority.
- Build new normal-runtime entry points around reusable modules; checkpoint scripts are tests, not the product.
- Keep debugging telemetry available but out of the normal presentation.

---

## 11. Immediate next move in a fresh chat

After reading this file, do **not** reopen CP19–23.

Start **Phase A / A1** by inspecting:

- `rebuild/firmware/main/main.cpp` (current probe display/touch baseline),
- `rebuild/firmware/main/probe19.cpp` (current serial command runtime),
- `rebuild/backend/kcore/runtime.py`,
- `rebuild/backend/kcore/host.py`,
- `rebuild/backend/kcore/providers.py`,
- `rebuild/docs/ARCHITECTURE.md`,
- build/CMake routing for the currently selected firmware entry point.

First objective: design and implement the real Kadence display/presence layer **without breaking the already-proven COM4 body runtime**.

Before asking the user to build/flash, commit the change on `kadence/rebuild-kade`, add an A1 gate where practical, and give the user **one command at a time**.

---

## 12. How the user should restart this in a fresh chat

The user can simply say:

> Read `rebuild/docs/KADENCE_HANDOVER.md` from my `neoncrucible/StackChanSource` repo on branch `kadence/rebuild-kade`, then continue the Kadence rebuild from the documented next step. You lead; one command at a time.

That should be sufficient to restore the project context.

---

## 13. Final reminder to future Kade

The hard infrastructure work was valuable, but the user did not spend days rebuilding Kadence to admire transport correctness.

The next work must produce **visible, audible, companion-like progress**.

Do not confuse “foundation proven” with “product finished” again.
