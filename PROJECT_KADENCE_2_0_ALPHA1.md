# Project Kadence 2.0 — Alpha 1

## Status — COMPLETE / FROZEN

**Alpha 1 was physically validated and closed on 20 Aug 2026.**

Base branch: `beta/project-kadence`

Validation PR: `#8`

Validated firmware revision:

`b51bd762eb315b7bc330db0a5f9ecc1daa2183da`

The stable Beta branch was not merged over or modified. Alpha 1 is retained as the proven low-latency transport baseline for the next Kadence 2.0 phase.

See `experiments/xiaozhi-backend/ALPHA1_CLOSEOUT.md` for the immutable close-out record.

## Alpha 1 question

> Can Kadence keep her existing robot-side wake, UI, audio, touch and safety behaviour while replacing the staged Windows transcript path with a Xiaozhi-compatible low-latency bidirectional conversation backend?

**Answer: yes.**

The final physical validation used the cleaned Kadence control protocol, OpenAI Realtime transcription, server-side Silero endpointing, Gemini Flash-Lite and Edge TTS. Kadence heard the fixed test phrase, accepted the server endpoint request, closed and flushed her own microphone path, transcribed correctly, answered `Twelve times seven is eighty-four`, spoke it through the existing device playback path and returned normally.

## Final gate decision

- **Gate A — reproducible backend:** PASSED.
- **Gate B — full bidirectional robot round trip:** PASSED physically.
- **Streaming ASR / server endpoint architecture:** PASSED physically and repeatedly.
- **Gate C — low-latency architecture:** ACCEPTED for Alpha 1 based on repeated endpoint/ASR measurements and physical audible responses. The originally proposed formal Beta-vs-Alpha T8 speaker benchmark was not instrumented and is explicitly deferred rather than claimed as measured.
- **Gate D — full Kadence identity/personality restoration:** deferred to the next development phase.
- **Gate E — persistent memory:** deferred to the next development phase.

Alpha 1 therefore closes as a **transport and latency architecture milestone**, not as the finished Kadence 2.0 product.

## Frozen Alpha 1 stack

- upstream backend: `xinnan-tech/xiaozhi-esp32-server`
- pinned upstream revision: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- robot transport: Xiaozhi version-1 `WebsocketProtocol`
- microphone uplink: 16 kHz mono Opus, 60 ms frames
- server VAD: Silero observation in manual mode
- server endpoint sustained-silence hold: **700 ms**
- device AFE endpoint fallback: **850 ms after local speech clears**
- final Opus flush: **180 ms**
- hard capture cap: **10 s**
- ASR: OpenAI Realtime `gpt-realtime-whisper`, 16 kHz -> 24 kHz PCM resampling
- LLM: Gemini `gemini-3.5-flash-lite`
- TTS: Edge `en-GB-SoniaNeural`
- Memory: `nomem`
- Intent: `nointent`
- MCP/model-directed robot movement: ignored

Do not tune these values on the frozen Alpha 1 branch.

## What Alpha 1 proved

### Realtime ASR

A ten-completed-turn natural-language stress run produced final transcription times between **0.485 s and 0.687 s after commit**, with a median of approximately **0.617 s**.

Prompts included factual questions, identity, jokes, longer natural questions and pop-culture questions. Recognition remained usable throughout.

### Endpointing

Before server endpoint handoff, one measured turn showed final server silence at `18:58:33` but robot `listen/stop` only at `18:58:37` — roughly four seconds of avoidable dead air.

With the frozen server endpoint architecture, completed stress-run endpoint requests landed between roughly **703 ms and 1015 ms** after confirmed Silero silence, with a median around **766 ms**. The normal case clustered near the configured 700 ms hold.

### Final cleaned-protocol validation

Final test on 20 Aug 2026:

- listen start: `20:00:29`
- first Realtime transcript delta: `20:00:31`
- proper Kadence endpoint request: **718 ms** confirmed Silero silence
- robot `listen/stop`: `20:00:32`, immediately following the endpoint request
- Realtime final transcript: **0.718 s after commit**
- LLM received: `What's twelve times seven?` at `20:00:33`
- first TTS sentence: `Twelve times seven is eighty-four` at `20:00:34`

This final run used the dedicated `type: "kadence"` control envelope documented in `experiments/xiaozhi-backend/KADENCE_CONTROL_PROTOCOL.md`; the temporary fake-error sentinel was no longer involved.

## Robot authority and safety invariants

Alpha 1 preserves these rules:

- wake word remains local to Kadence;
- a server endpoint request cannot directly start TTS or arbitrarily stop hardware;
- firmware remains authoritative for the microphone capture gate;
- firmware performs its own final Opus flush and ordinary Xiaozhi `listen/stop`;
- local AFE and the ten-second cap remain independent fallbacks;
- head-swipe cancellation remains available;
- MCP/model output cannot command arbitrary servo coordinates;
- Beta remains the rollback path;
- no API keys or personal memory are committed to Git.

## Known non-blocking items carried forward

- Python 3.10 reaches Google support EOL on 4 Oct 2026; move the backend environment to Python 3.11+ in a later maintenance pass.
- idle Xiaozhi connections still recycle after the pinned server timeout unless application keepalive is added;
- simplified no-manager mode can log a cosmetic chat-title generation failure on disconnect;
- formal T8 first-speaker-sample instrumentation and a strict Beta-vs-Alpha A/B benchmark remain useful future performance work.

None of these invalidated the Alpha 1 transport proof.

## Next phase

Future work starts from this frozen baseline rather than continuing to mutate it. Priority order:

1. restore the full Kadence personality/system prompt;
2. preserve the preferred British voice while evaluating richer TTS only if latency remains acceptable;
3. add backend-local short memory as the first memory experiment;
4. design robot-owned SD identity/memory with atomic writes and backups;
5. add safe fixed MCP actions and expression mapping;
6. add heartbeat/idle-connection cleanup and later dependency maintenance.

**Alpha 1 is closed.**
