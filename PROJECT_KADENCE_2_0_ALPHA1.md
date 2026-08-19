# Project Kadence 2.0 — Alpha 1

## Status

Experimental development line. Do **not** flash or merge over the signed/stable Kadence Beta path until the Alpha 1 gates below pass.

Base branch: `beta/project-kadence`

Purpose: replace the bespoke staged Windows transcript pipeline with a Xiaozhi-compatible streaming conversation backend while preserving Kadence's existing robot identity, wake behaviour, display, motion, touch, safety constraints and rollback path.

## Why 2.0

Kadence Beta already keeps the ESP32-S3 microphone/AFE warm and maintains a preconnected WebSocket, but the turn still becomes staged at end-of-speech: capture stops, final Opus is flushed, the robot waits for a completed transcript, then the Windows pipeline advances through LLM and TTS.

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
- server exposes `ws://<LAN-IP>:8000/xiaozhi/v1/`;
- no manager-api, MySQL or Redis dependency is required for the first experiment.

### Gate B — protocol connection

- an experimental Kadence firmware build connects to the local Xiaozhi endpoint;
- microphone Opus reaches the backend;
- STT result is received;
- TTS Opus returns to the CoreS3 and plays through the existing speaker path.

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

1. Run `experiments/xiaozhi-backend/bootstrap_windows.ps1`.
2. Copy/edit the generated `data/.config.yaml`; add only the API key needed for the chosen test LLM.
3. Start the pinned backend and confirm its WebSocket endpoint.
4. Do **not** flash Alpha firmware yet if the backend itself is unhealthy.
5. Once backend is clean, implement the smallest possible firmware protocol adapter and flash only the `kadence/2.0-alpha-1` build.
6. Prove round-trip speech before adding personality, memory, MCP or new motion.
7. Run the fixed latency test set and compare against Beta.

## Out of scope for Alpha 1

- new controller hardware;
- ESP32-local generative LLM inference;
- vision/camera work;
- long-term vector memory;
- theme system;
- new robot motions;
- replacing the stable Beta branch.

The Alpha 1 question is deliberately narrow:

> Can Kadence keep everything that makes her Kadence while gaining Xiaozhi's low-latency streaming conversation architecture?
