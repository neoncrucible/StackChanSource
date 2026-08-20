# Kadence 2.0 Alpha 1 — Close-out

Status: **VALIDATED / FROZEN**

Date closed: **20 Aug 2026**

## Validated revision

Firmware / transport revision:

`b51bd762eb315b7bc330db0a5f9ecc1daa2183da`

Commit message:

`Alpha 1: formalize endpoint control and freeze latency baseline`

## CI proof

- Factory firmware workflow: **#200** — success
- Factory workflow run: `32404344702`
- Servo yaw checkpoint workflow: **#126** — success
- Servo workflow run: `32404344541`

Factory artifact:

- artifact name: `stackchan-factory-firmware`
- artifact id: `9419984921`
- SHA-256: `6d60d62d08389987a4d3c137ecc12d8cda4cffe7700c10777ebe12f167254cab`

## Upstream baseline

Pinned Xiaozhi backend revision:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

The pin is part of the Alpha 1 baseline and must not be silently advanced when reproducing this result.

## Final physical validation

Fixed phrase:

`Kadence, what is twelve times seven?`

Observed server sequence:

- listen start `20:00:29`
- first Realtime transcript delta `20:00:31`
- Kadence endpoint control request after **718 ms** confirmed Silero silence
- robot `listen/stop` `20:00:32`
- Realtime final transcript **0.718 s after commit**: `What's twelve times seven?`
- LLM received the transcript `20:00:33`
- TTS generated `Twelve times seven is eighty-four` `20:00:34`

The response played physically through Kadence and the turn completed normally.

## Repeated ASR evidence

A separate ten-completed-turn natural-language run measured Realtime finalization between **0.485 s and 0.687 s after commit**, median approximately **0.617 s**.

Endpoint requests for those completed turns ranged from **703 ms to 1015 ms** after confirmed Silero silence, median approximately **766 ms**.

This demonstrates that the low-latency result was repeatable rather than a one-off smoke test.

## Architecture accepted

Alpha 1 closes with these decisions:

- keep Xiaozhi version-1 bidirectional WebSocket transport;
- keep 16 kHz / 60 ms Opus robot uplink;
- keep OpenAI Realtime transcription;
- keep Windows Silero as preferred endpoint detector;
- keep 700 ms continuous-silence server endpoint hold;
- keep ESP32 AFE endpoint as fallback;
- keep 10 s hard capture cap;
- keep robot authoritative for microphone stop/flush;
- keep dedicated `type: "kadence"`, version `1` control messages;
- do not use transport errors as control messages;
- keep model-directed arbitrary hardware movement disabled.

## Explicitly deferred

Alpha 1 does **not** claim completion of:

- formal device-side T8 first-speaker-sample instrumentation;
- strict Beta-vs-Alpha A/B benchmark;
- full Kadence personality restoration;
- persistent memory;
- MCP actions / expression mapping;
- idle heartbeat cleanup;
- Python 3.11+ migration.

These belong to later work and must not be retroactively described as Alpha 1 results.

## Rollback / branch policy

- `beta/project-kadence` remains unchanged and is still the stable rollback line.
- `kadence/2.0-alpha-1` is now a frozen historical baseline.
- future feature work should branch from the validated Alpha 1 result rather than mutating the frozen experiment.
- PR #8 is the validation record, not authorization to merge Alpha 1 over Beta.

**Project Kadence 2.0 Alpha 1 is complete.**
