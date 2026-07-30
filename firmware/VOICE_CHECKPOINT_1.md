# Voice Checkpoint 1

Robot microphone and speaker remain the only physical voice input and output. Wake word: `Kadence`, pronounced like `Cadence`.

## Signed-off Voice Checkpoint 1B

Corrective commit `ec8902d41d988c94746530ef466be410cbda92f7` physically passed:

- real on-device `Kadence` wake detection;
- green listening frame and chirp;
- green/red pulse;
- ten-second timeout and wake-word rearm;
- either head swipe cancels immediately;
- explicit boot rest `[80,300]` and torque release;
- wake cancels active idle movement safely;
- repeated wake, timeout, swipe and idle cycles without an ESP crash or visible memory leak.

## Voice Checkpoint 1C — transcript transport

This candidate adds only:

```text
StackChan onboard microphone
→ 16 kHz mono Opus, 60 ms frames
→ Xiaozhi version-1 WebSocket
→ Windows Faster Whisper
→ transcript returned to robot serial
```

The firmware:

- starts the board's stored Wi-Fi connection after the signed-off boot sequence;
- discovers the Windows transcript server by UDP broadcast on port `45872`;
- derives the WebSocket address from the reply source and opens `/kadence/v1` on port `8000`;
- never compiles a PC address, Wi-Fi password or service credential;
- starts microphone encoding only after the chirp and WebSocket handshake;
- streams raw Opus packets from the existing `AudioService` send queue;
- submits a ten-second sample for transcription;
- logs `WINDOWS TRANSCRIPT: ...` when the server returns `stt` JSON;
- lets either head swipe cancel and discard the active sample;
- preserves boot rest, idle movement, calibration and torque policy.

The paired Windows implementation is in `neoncrucible/Droid-dev` draft PR #9.

## Deliberate limits

- no Gemini request;
- no Edge TTS or response audio;
- no PC microphone or PC speaker fallback;
- no voice-triggered servo command;
- no model-owned coordinates;
- no merge until CI and physical robot-to-Windows transcript testing pass.
