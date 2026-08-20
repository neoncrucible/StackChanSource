# Kadence 2.0 Alpha 1 — Windows Runbook

This experiment lives on `kadence/2.0-alpha-1`. The known-good `beta/project-kadence` branch remains untouched and is the rollback point.

Current Alpha baseline (20 Aug 2026):

- pinned Xiaozhi backend `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`;
- 16 kHz / 60 ms Opus robot uplink over the retained warm Xiaozhi WebSocket;
- Windows Silero endpoint observation with a frozen `700 ms` sustained-silence hold;
- OpenAI Realtime `gpt-realtime-whisper` transcription (16 kHz -> 24 kHz PCM resampled in-flight);
- Gemini `gemini-3.5-flash-lite`;
- Edge TTS `en-GB-SoniaNeural`;
- TTS Opus returned through the robot's existing `AudioService` decode/playback queues;
- no memory, no intent LLM, no MCP robot actions.

The endpoint control contract is documented in `KADENCE_CONTROL_PROTOCOL.md`.

## 0. Before starting

Stop any older Kadence Windows voice server. Alpha 1 reuses UDP discovery port `45872`; the launcher deliberately fails instead of silently competing for the port.

Do not flash an Alpha firmware image unless the corresponding PR #8 factory firmware build is green.

## 1. Pull Alpha

```powershell
git fetch origin
git switch kadence/2.0-alpha-1
git pull
```

Then enter:

```powershell
cd experiments\xiaozhi-backend
```

## 2. Bootstrap once

```powershell
.\bootstrap_windows.ps1
```

The bootstrap creates the ignored runtime at:

`.runtime\xiaozhi-esp32-server`

and checks out exactly:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

It also creates the Conda environment `kadence2-xiaozhi` and the local runtime config.

## 3. Start the proven Alpha stack

```powershell
.\start_windows.ps1
```

`start_windows.ps1` now performs the full reproducible startup path:

1. verifies the pinned Xiaozhi revision;
2. applies the narrowly guarded Gemini/Silero runtime compatibility patches;
3. securely injects missing OpenAI/Gemini credentials into the ignored local config;
4. installs/refreshes the tracked Kadence Realtime ASR provider automatically;
5. preserves the frozen `700 ms` endpoint hold;
6. locates the working standalone FFmpeg build when present;
7. starts the UDP discovery bridge and Xiaozhi server.

Real API keys are never committed or printed. The checked-in config contains placeholders only.

If the ordinary PowerShell session cannot find `conda`, add the existing Miniconda paths to that shell first:

```powershell
$env:Path = "$env:USERPROFILE\miniconda3;$env:USERPROFILE\miniconda3\Scripts;$env:USERPROFILE\miniconda3\condabin;$env:Path"
```

No LAN-IP edit is required. Kadence discovers the PC through the retained `KADENCE_DISCOVER_V1` UDP bridge and connects to `/xiaozhi/v1/`.

Expected ASR startup markers include:

```text
初始化组件: asr成功 OpenaiRealtimeASR
K2 ASR LIVE ready: model=gpt-realtime-whisper, 16k->24k PCM, endpoint=700ms
```

## 4. Optional PC-side preflight

In a second PowerShell from this folder:

```powershell
.\test_backend.ps1
```

It checks TCP `8000` plus the exact UDP discovery request/reply used by the robot.

## 5. Firmware behaviour

Alpha firmware preserves:

- local `Kadence` wake word;
- chirp/listening UI;
- touch and swipe cancellation;
- motion/torque safety behaviour;
- on-device AFE endpoint as fallback;
- ten-second capture safety cap;
- warm Xiaozhi WebSocket;
- final 180 ms Opus flush before `listen/stop`;
- downstream Xiaozhi TTS playback through the existing robot speaker path.

Server-side Silero now sends a proper versioned Kadence `endpoint` control message after sustained silence. The server never directly starts a reply while the robot is still recording; firmware remains authoritative for closing capture and sending Xiaozhi stop-listening.

## 6. Physical smoke test

Use:

`Kadence, what is twelve times seven?`

Useful server markers:

- `K2 ASR LIVE first audio frame`
- `K2 ASR LIVE first transcript delta ...`
- `K2 ENDPOINT requested after ...`
- `K2 ASR LIVE audio buffer committed`
- `K2 ASR LIVE completed ... after commit`
- `K2 ASR LIVE -> chat: ...`

Useful firmware markers:

- `K2 LATENCY T1` — first microphone Opus sent;
- `Kadence control endpoint request received` — server endpoint reached device;
- `K2 LATENCY T2` — robot ended capture and began final Opus flush;
- `K2 LATENCY T3` — STT received by firmware;
- `K2 LATENCY T7` — first returned TTS Opus queued;
- `TTS playback drained` — completed turn released back to the UI.

The validated 20 Aug baseline is recorded in `LATENCY_TEST.md`.

## 7. Stop conditions

Return to the Beta image if any of these recur:

- uncontrolled servo movement;
- repeated reboot;
- microphone/AFE fails to recover after a turn;
- persistent audio feedback;
- cancellation no longer stops the turn;
- model output attempts raw hardware control;
- credentials or personal memory appear in tracked/logged material.

## Still out of scope

Until the transport baseline is formally signed off, do not mix in:

- persistent memory;
- SD-card identity storage;
- MCP motion/actions;
- emotion mapping;
- vision;
- new expressions/hardware.
