# Project Kadence 2.0 — Alpha 1

## Status

Experimental development line. Do **not** merge over the signed/stable Kadence Beta path until the remaining Alpha gates below pass.

Base branch: `beta/project-kadence`

Draft PR: `#8`

Purpose: replace the bespoke staged Windows transcript pipeline with a Xiaozhi-compatible bidirectional conversation backend while preserving Kadence's existing robot identity, wake behaviour, display, motion, touch, safety constraints and rollback path.

### Gate status — 20 Aug 2026

- **Gate A — reproducible backend:** passed on the Windows test machine.
- **Gate B — complete bidirectional robot round trip:** passed physically. Robot microphone audio reaches Xiaozhi, transcript reaches the LLM, TTS returns as Opus and plays through Kadence's existing speaker path.
- **Streaming-ASR/endpoint sub-gate:** passed physically. OpenAI Realtime transcription plus server-side Silero endpointing removed the multi-second local endpoint delay seen in earlier turns.
- **Gate C — full ten-utterance Beta-vs-Alpha latency benchmark:** still pending. The proven endpoint turn is recorded in `experiments/xiaozhi-backend/LATENCY_TEST.md`, but T8 and the full A/B set still need measurement.
- **Gate D — full Kadence identity restoration:** not started.
- **Gate E — memory experiment:** not started.

### Implemented in this Alpha branch

- pinned self-hosted Xiaozhi backend bootstrap;
- Windows launcher and Kadence UDP discovery bridge;
- secure local injection of API credentials;
- tracked OpenAI Realtime ASR provider installed automatically at startup;
- existing Xiaozhi `WebsocketProtocol` retained on the CoreS3;
- incoming Xiaozhi TTS Opus routed into the existing `AudioService` decoder/playback path;
- versioned Kadence server-to-device control namespace for endpoint requests;
- server-side Silero endpoint request after a frozen `700 ms` sustained-silence hold;
- ESP32 AFE endpoint and ten-second capture cap retained as independent fallbacks;
- completed turn withheld from the existing Beta UI state machine until STT exists, TTS has stopped and playback has drained;
- MCP/model-directed hardware actions ignored in Alpha 1;
- T1/T2/T3/T7 device latency markers;
- fixed A/B latency benchmark;
- Alpha-branch ESP-IDF 5.5.4 CI build trigger and explicit commit status reporting.

## Why 2.0

Kadence Beta already keeps the ESP32-S3 microphone/AFE warm and maintains a preconnected WebSocket, but the old turn becomes staged at end-of-speech. Alpha 1 now keeps audio flowing to the backend during the utterance, lets Realtime ASR begin decoding before the user has finished, and uses server-side Silero to request the endpoint when the ESP32's local detector is slow.

The important boundary remains on the robot: a server endpoint request does **not** directly stop recording or start TTS. Firmware closes its own capture gate, performs the final Opus flush, then sends the ordinary Xiaozhi stop-listening message.

The Kadence-specific control envelope is documented in `experiments/xiaozhi-backend/KADENCE_CONTROL_PROTOCOL.md`.

## Upstream pin

Backend: `xinnan-tech/xiaozhi-esp32-server`

Pinned revision for Alpha 1 baseline:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

Do not silently update this pin during Alpha 1. Upstream changes are evaluated deliberately after a repeatable baseline exists.

## Proven latency stack

The current frozen Alpha baseline is:

- robot uplink: 16 kHz mono Opus, 60 ms frames;
- VAD: Silero observation on the Windows backend;
- server endpoint hold: `700 ms` continuous Silero silence after real speech;
- ASR: OpenAI Realtime `gpt-realtime-whisper` (16 kHz -> 24 kHz PCM in-flight resampling);
- LLM: Gemini `gemini-3.5-flash-lite`;
- TTS: Edge `en-GB-SoniaNeural`;
- memory: `nomem`;
- intent: `nointent`;
- MCP/model-directed movement: ignored.

The successful 19:25 physical proof turn produced a server endpoint after `704 ms` confirmed silence, Realtime final transcript `0.515 s` after commit, immediate LLM dispatch, and first TTS sentence in the next logged second. These server timings do not substitute for the pending T8 physical-speaker benchmark.

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

### Gate A — backend boots reproducibly — PASSED

- pinned Xiaozhi server is cloned locally;
- Python 3.10 environment is created;
- required Opus/FFmpeg dependencies are present;
- Kadence override config is loaded from `data/.config.yaml`;
- tracked Realtime ASR provider is installed automatically by the launcher;
- server listens on port `8000` and exposes `/xiaozhi/v1/`;
- no manager-api, MySQL or Redis dependency is required for the experiment.

### Gate B — protocol connection and full turn — PASSED

- Alpha firmware connects through retained Kadence UDP discovery;
- microphone Opus reaches the backend;
- Realtime STT completes;
- LLM response is generated;
- TTS Opus returns to the CoreS3 and plays through the existing speaker path;
- completion returns cleanly to the existing Kadence idle/wake path.

### Gate C — measured latency win — IN PROGRESS

Run the same ten utterances against:

1. current Kadence Beta pipeline;
2. Kadence 2.0 Xiaozhi backend.

Capture these timestamps where available:

- T0 wake detected
- T1 first microphone frame sent
- T2 speech endpoint accepted by robot
- T3 final/usable STT
- T4 LLM request starts
- T5 first LLM token/chunk
- T6 first TTS request/chunk
- T7 first TTS audio returned to robot
- T8 first speaker sample

Primary metric: **T8 - T2** (end-of-user-speech to first audible reply).

The endpoint architecture has already shown a material qualitative win: one pre-handoff test left roughly four seconds between final server silence and robot stop, while the validated handoff requested endpoint after ~700 ms and the robot stopped immediately. The complete ten-utterance median and physical T8 measurements are still required before Gate C is formally closed.

### Gate D — identity restoration

Only after the streaming baseline is frozen and the cleanup build passes:

- restore the full Kadence system/persona prompt;
- keep the preferred British voice;
- map Xiaozhi emotion/tool events onto Kadence expressions and safe motion presets;
- keep robot behaviour deterministic in firmware even when the model chooses an action.

### Gate E — memory experiment

Start with backend-local `mem_local_short` to validate summarised continuity.

Robot-owned SD memory is a later gate. Target interface:

- `self.kadence.memory.read`
- `self.kadence.memory.write`
- `self.kadence.memory.backup`

The long-term rule is that external LLMs may reason for Kadence, but Kadence's durable identity/memory should not depend on a single model provider.

## Current test order

1. Pull `kadence/2.0-alpha-1`.
2. Run `experiments/xiaozhi-backend/bootstrap_windows.ps1` once on a fresh runtime.
3. Run `experiments/xiaozhi-backend/start_windows.ps1`; it patches the pinned runtime, installs the Realtime provider and starts discovery/server services.
4. Use only a PR #8 firmware artifact whose ESP-IDF factory build is green.
5. Run the fixed ten-utterance benchmark in `LATENCY_TEST.md` without changing the frozen timing values.
6. Record T8/device-speaker timing before declaring Gate C complete.
7. Only then restore full personality, memory, MCP or new robot behaviour.

## Out of scope for Alpha 1

- new controller hardware;
- ESP32-local generative LLM inference;
- vision/camera work;
- long-term vector memory;
- theme system;
- new robot motions;
- replacing the stable Beta branch.

The Alpha 1 question remains deliberately narrow:

> Can Kadence keep everything that makes her Kadence while gaining Xiaozhi's low-latency conversation architecture?

The answer is now **yes for the transport architecture**; the remaining Alpha work is measurement, cleanup and then restoration of the richer Kadence layer.
