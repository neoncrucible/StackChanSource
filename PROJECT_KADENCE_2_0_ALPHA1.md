# Project Kadence 2.0 — Alpha 1

## Status

Experimental development line. Do **not** merge over the signed/stable Kadence Beta path until the Alpha 1 gates below pass.

Base branch: `beta/project-kadence`

Draft PR: `#8`

Purpose: replace the bespoke staged Windows transcript pipeline with a Xiaozhi-compatible bidirectional conversation backend while preserving Kadence's existing robot identity, wake behaviour, display, motion, touch, safety constraints and rollback path.

### Implemented in this Alpha branch

- pinned self-hosted Xiaozhi backend bootstrap;
- Windows launcher and Kadence UDP discovery bridge;
- secure local injection of smoke-test API credentials;
- existing Xiaozhi `WebsocketProtocol` retained on the CoreS3;
- incoming Xiaozhi TTS Opus routed into the existing `AudioService` decoder/playback path;
- completed turn withheld from the unchanged Beta UI state machine until STT exists, TTS has stopped and playback has drained;
- MCP/model-directed hardware actions ignored in Alpha 1;
- T1/T2/T3/T7 device latency markers;
- fixed A/B latency benchmark;
- Alpha-branch ESP-IDF 5.5.4 CI build trigger and explicit commit status reporting.

## Why 2.0

Kadence Beta already keeps the ESP32-S3 microphone/AFE warm and maintains a preconnected WebSocket, but the turn becomes staged at end-of-speech: capture stops, final Opus is flushed, the robot waits for a completed transcript, then the Windows pipeline advances through LLM and TTS.

Xiaozhi's protocol is designed as a bidirectional conversation session: audio upstream, state/control messages and streamed audio downstream. Alpha 1 tests whether adopting that orchestration materially reduces time-to-first-audio without throwing away Kadence's existing robot work.

## Upstream pin

Backend: `xinnan-tech/xiaozhi-esp32-server`

Pinned revision for Alpha 1 baseline:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

Do not silently update this pin during Alpha 1. Upstream changes are evaluated deliberately after a repeatable baseline exists.

## Non-negotiable invariants

Alpha 1 must preserve:

- local Kadence wake-word path;
- current chirp/listening UX unless a test explicitly isolates it;
- current face and Project Kadence identity;
- current motion controller and safe fixed motion presets;
- touch behaviour;
- torque-release/idle safety behaviour;
- no model-generated raw servo coordinates;
- existing Beta branch as immediate rollback;
- no API keys, tokens or personal memory committed to Git.

## Alpha 1 gates

### Gate A — backend boots reproducibly

- pinned Xiaozhi server is cloned locally;
- Python 3.10 environment is created;
- required Opus/FFmpeg dependencies are present;
- Kadence override config is loaded from `data/.config.yaml`;
- server listens on port `8000` and exposes `/xiaozhi/v1/`;
- no manager-api, MySQL or Redis dependency is required for the first experiment.

### Gate B — protocol connection

- Alpha firmware connects to the local Xiaozhi endpoint through the retained Kadence UDP discovery mechanism;
- microphone Opus reaches the backend;
- STT result is received;
- TTS Opus returns to the CoreS3 and plays through the existing speaker path;
- completion returns cleanly to the existing Kadence idle/wake path.

No motion, memory or MCP work begins until this passes.

### Gate C — measured latency win

Run the same ten utterances against:

1. current Kadence Beta pipeline;
2. Kadence 2.0 Xiaozhi backend.

Capture these timestamps where available:

- T0 wake detected
- T1 first microphone frame sent
- T2 speech endpoint detected
- T3 final/usable STT
- T4 LLM request starts
- T5 first LLM token/chunk
- T6 first TTS request/chunk
- T7 first TTS audio returned
- T8 first speaker sample

Primary metric: **T8 - T2** (end-of-user-speech to first audible reply).

Secondary metrics: wake-to-capture, STT completion, first LLM output and first TTS audio.

Alpha 1 succeeds if the new path is consistently and materially faster without degrading recognition or stability.

The first smoke-test ASR (`OpenaiASR`) is intentionally simple rather than fully streaming. After Gate B passes, evaluate a genuine streaming-ASR provider separately so protocol integration and provider latency are not confused with each other.

### Gate D — identity restoration

Only after the streaming baseline is proven:

- restore the full Kadence system/persona prompt;
- restore the preferred British voice;
- map Xiaozhi emotion/tool events onto Kadence expressions and safe motion presets;
- keep robot behaviour deterministic in firmware even when the model chooses an action.

### Gate E — memory experiment

Start with backend-local `mem_local_short` to validate summarised continuity.

Robot-owned SD memory is a later gate. Target interface:

- `self.kadence.memory.read`
- `self.kadence.memory.write`
- `self.kadence.memory.backup`

The long-term rule is that external LLMs may reason for Kadence, but Kadence's durable identity/memory should not depend on a single model provider.

## Morning test order

1. Check draft PR `#8`; only use the Alpha firmware if its ESP-IDF build is green.
2. Pull `kadence/2.0-alpha-1`.
3. Run `experiments/xiaozhi-backend/bootstrap_windows.ps1`.
4. Run `experiments/xiaozhi-backend/start_windows.ps1`; paste the two smoke-test API keys when securely prompted (or set the documented environment variables beforehand).
5. Confirm the pinned backend starts cleanly before flashing anything.
6. Flash only the Alpha artifact and perform one simple round-trip speech test.
7. If the first turn is clean, run the fixed latency test set and compare against Beta.
8. Only after the transport wins do we add full personality, memory, MCP or new robot behaviour.

## Out of scope for Alpha 1

- new controller hardware;
- ESP32-local generative LLM inference;
- vision/camera work;
- long-term vector memory;
- theme system;
- new robot motions;
- replacing the stable Beta branch.

The Alpha 1 question is deliberately narrow:

> Can Kadence keep everything that makes her Kadence while gaining Xiaozhi's low-latency conversation architecture?
