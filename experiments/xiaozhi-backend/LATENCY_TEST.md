# Kadence 2.0 Alpha 1 — Latency Benchmark / Close-out Record

## Alpha 1 decision

Alpha 1 is **accepted and frozen** as the proven transport/latency architecture baseline.

The original benchmark design called for a formal Beta-vs-Alpha comparison using device-side T8 (first speaker sample). T8 was not instrumented during Alpha 1, so that comparison is **deferred** rather than claimed as completed.

What Alpha 1 did measure repeatedly is strong enough to close the transport experiment:

- server-side endpoint handoff removed multi-second robot dead air;
- OpenAI Realtime transcription consistently finalized in well under one second after commit;
- Kadence physically spoke correct responses and returned to idle;
- the cleaned dedicated Kadence control message reproduced the proven timing without the temporary error sentinel.

## Frozen Alpha timing configuration

- robot microphone uplink: 16 kHz mono Opus, 60 ms frames
- server VAD: Silero (`threshold 0.5`, `threshold_low 0.3`, `min_silence_duration_ms 200`)
- server endpoint sustained-silence hold: **700 ms**
- robot AFE silence fallback: **850 ms after local speech clears**
- robot final Opus flush: **180 ms**
- robot capture hard cap: **10 s**
- ASR: OpenAI Realtime `gpt-realtime-whisper`, 16 kHz -> 24 kHz PCM resampling
- LLM: Gemini `gemini-3.5-flash-lite`
- TTS: Edge `en-GB-SoniaNeural`

These values are frozen for Alpha 1.

## Pre-cleanup endpoint proof

Fixed utterance: `What is twelve times seven?`

| Event | Result |
|---|---:|
| listen start | 19:25:40 |
| first Realtime transcript delta | 1.563 s after first streamed audio frame |
| server endpoint request | 704 ms confirmed Silero silence |
| robot `listen/stop` | immediate next logged event |
| Realtime final transcript | 0.515 s after commit |
| LLM received transcript | 19:25:44 |
| first TTS sentence | 19:25:45 |

Immediately before server endpoint handoff existed, another test showed final server silence at `18:58:33` and robot `listen/stop` only at `18:58:37`, demonstrating the multi-second local endpoint delay the new architecture removed.

## Ten-completed-turn natural-language stress run

The stress run included factual questions, identity, jokes, guard-rail discussion and pop-culture questions.

### Realtime ASR finalization after commit

Measured values (seconds):

`0.515, 0.672, 0.687, 0.609, 0.485, 0.656, 0.672, 0.485, 0.579, 0.625`

- minimum: **0.485 s**
- maximum: **0.687 s**
- median: **~0.617 s**

### Server endpoint request after confirmed Silero silence

Measured values (milliseconds) for the ten completed turns:

`704, 719, 781, 703, 812, 750, 812, 1015, 703, 829`

- minimum: **703 ms**
- maximum: **1015 ms**
- median: **~766 ms**

The distribution is consistent with a 700 ms sustained-silence hold plus frame/scheduling granularity.

### Stress-run edge case

One separate turn using the temporary fake-error endpoint sentinel disconnected at the endpoint rather than completing normally. Subsequent turns recovered, but the event reinforced the decision to replace the sentinel with a dedicated Kadence control envelope.

The final cleanup build no longer uses the fake error path.

## Final cleaned-protocol validation — 20 Aug 2026

Firmware revision:

`b51bd762eb315b7bc330db0a5f9ecc1daa2183da`

Fixed utterance: `What is twelve times seven?`

| Event | Result |
|---|---:|
| listen start | 20:00:29 |
| first Realtime transcript delta | 1.734 s after first audio frame |
| dedicated Kadence endpoint request | **718 ms** confirmed Silero silence |
| robot `listen/stop` | 20:00:32, immediately after endpoint request |
| Realtime final transcript | **0.718 s after commit** |
| LLM received transcript | 20:00:33 |
| first TTS sentence | 20:00:34 — `Twelve times seven is eighty-four` |

This is the final Alpha 1 validation run.

## Deferred measurement

The following remains useful future work but is not claimed as Alpha 1 data:

- device-side **T8** first physical speaker sample instrumentation;
- strict same-room ten-utterance Beta-vs-Alpha A/B timing;
- end-to-end wake-to-audible-response median and percentile reporting.

Those measurements can be added in a later performance phase without reopening the frozen Alpha 1 transport design.
