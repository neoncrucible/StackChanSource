# Kadence 2.0 Alpha 1 — Morning Runbook

This experiment keeps `beta/project-kadence` untouched. All firmware and server work here belongs to `kadence/2.0-alpha-1`.

## 0. Before anything else

Stop the existing Kadence Windows voice server. Alpha 1 reuses UDP discovery port `45872`; the launcher deliberately fails rather than silently fighting the old service for that port.

Do not flash the Alpha firmware until the GitHub firmware build for draft PR #8 is green.

## 1. Get the Alpha branch

```powershell
git fetch origin
git switch kadence/2.0-alpha-1
git pull
```

## 2. Bootstrap the pinned Xiaozhi backend

From the repository root:

```powershell
cd experiments\xiaozhi-backend
.\bootstrap_windows.ps1
```

The script creates a local, ignored runtime at:

`experiments\xiaozhi-backend\.runtime\xiaozhi-esp32-server`

and checks out exactly:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

It also creates the local config at:

`.runtime\xiaozhi-esp32-server\main\xiaozhi-server\data\.config.yaml`

## 3. Start the backend

```powershell
.\start_windows.ps1
```

On the first run the launcher securely prompts for the two smoke-test credentials if they are not already available as environment variables:

- `KADENCE_OPENAI_API_KEY` — speech recognition;
- `KADENCE_GEMINI_API_KEY` — test LLM.

The typed values are written only into the ignored `.runtime` config. They are never written into the tracked example file or printed to the console.

No LAN-IP edit is required. Kadence retains her existing UDP discovery behaviour; the launcher answers the discovery request and points the robot at this PC's Xiaozhi endpoint automatically.

Alpha 1 deliberately starts with:

- OpenAI `gpt-4o-mini-transcribe` ASR;
- Gemini `gemini-2.0-flash` test LLM;
- `en-GB-SoniaNeural` Edge TTS;
- no memory;
- no intent LLM;
- no MCP robot actions.

That is a smoke-test stack. Provider/streaming-ASR tuning comes after a complete robot round trip works.

Expected launcher behaviour:

- pinned revision is verified;
- UDP `45872` discovery bridge starts;
- Xiaozhi listens on TCP `8000`;
- the bridge tells Kadence to use `/xiaozhi/v1/`;
- the console prints the Xiaozhi service startup logs.

Leave this window running.

## 4. Flash only the Alpha build

Use the firmware artifact produced for draft PR #8 once CI is green. Keep the known-good Beta image available for immediate rollback.

The Alpha firmware changes only the voice transport behaviour:

- existing local wake word remains;
- existing chirp/VAD/capture cutoff remains;
- existing motion/touch/torque code remains;
- upstream Xiaozhi `WebsocketProtocol` remains the transport;
- incoming Xiaozhi TTS Opus is now pushed into the existing `AudioService` decoder/playback queue;
- MCP and model-directed motion are ignored;
- the old UI state machine is released only after STT exists, TTS has stopped, and playback queues have drained.

## 5. First physical test

Do **one** simple turn first:

`Kadence, what is twelve times seven?`

Watch both ESP-IDF serial output and Xiaozhi server output.

Useful firmware markers:

- `K2 LATENCY T1` — first microphone Opus sent
- `K2 LATENCY T2` — end-of-speech submitted
- `K2 LATENCY T3` — STT received
- `K2 LATENCY T7` — first returned TTS Opus queued
- `TTS playback drained` — device-side response completed

If she hears, answers and returns to idle cleanly, move to `LATENCY_TEST.md`.

## 6. Stop immediately if

- the CoreS3 repeatedly reboots;
- AFE/audio fails to recover after a turn;
- TTS feeds back into a new wake/capture;
- speech does not stop after a head-swipe cancellation;
- motion changes unexpectedly.

Return to `beta/project-kadence` if a stop condition appears repeatedly.

## What Alpha 1 is NOT testing yet

Do not add these until the round-trip/latency gate passes:

- persistent memory;
- SD-card identity storage;
- MCP motion/actions;
- emotion mapping;
- vision;
- new expressions;
- new hardware.
