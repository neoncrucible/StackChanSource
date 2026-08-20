# Kadence 2.0 Alpha 1 — Latency Benchmark

## Rule

Compare the existing Kadence Beta path and the Xiaozhi-backed Alpha path using the **same room, microphone position, Wi-Fi, speaking distance and ten utterances**.

Do not add memory, MCP, new animations or personality changes until the baseline comparison is complete.

## Frozen Alpha timing configuration

The following values were frozen after the successful physical endpoint test on **20 Aug 2026**:

- robot microphone uplink: 16 kHz mono Opus, 60 ms frames;
- server VAD: Silero (`threshold 0.5`, `threshold_low 0.3`, `min_silence_duration_ms 200`);
- server endpoint sustained-silence hold: **700 ms**;
- robot on-device AFE silence fallback: **850 ms after its own speech state clears**;
- robot final Opus flush after endpoint: **180 ms**;
- robot capture hard cap: **10 seconds**;
- ASR: OpenAI Realtime `gpt-realtime-whisper`, with 16 kHz -> 24 kHz PCM resampling;
- LLM: Gemini `gemini-3.5-flash-lite`;
- TTS: Edge `en-GB-SoniaNeural`.

Do not tune these values during the ten-utterance A/B run. Change one variable at a time only after the baseline is recorded.

## Validated endpoint proof turn — 20 Aug 2026

Fixed utterance: `What is twelve times seven?`

The final pre-cleanup physical run produced:

| Event | Server timestamp / measured interval |
|---|---:|
| listen start | 19:25:40 |
| first Realtime transcript delta | 19:25:42 (`1.563 s` after first streamed audio frame) |
| final Silero silence state | 19:25:42 |
| server endpoint request | **704 ms** confirmed Silero silence |
| robot `listen/stop` received by server | 19:25:43, immediately after endpoint request |
| Realtime final transcript | **0.515 s after commit** |
| LLM received `What's twelve times seven?` | 19:25:44 |
| first TTS sentence generated | 19:25:45 (`Twelve times seven is eighty-four`) |

This run proves the endpoint handoff removed the major dead-air source seen immediately beforehand. In the 18:58 test, server Silero reached final silence at `18:58:33` but the robot did not send `listen/stop` until `18:58:37` — roughly four seconds later. With the 700 ms server endpoint handoff, the stop followed in the next timestamped second.

This is **not yet the full Gate C result** because the server log does not prove T8 (first physical speaker sample) and the complete ten-utterance Beta-vs-Alpha A/B set has not been recorded. It is the frozen Alpha tuning baseline used for that test.

## Fixed utterances

1. `What time is it?`
2. `Tell me a very short joke.`
3. `What is twelve times seven?`
4. `Explain what DNS does in one sentence.`
5. `Who are you?`
6. `Give me three colours.`
7. `What does HTTP stand for?`
8. `Tell me one fact about the Moon.`
9. `Say hello to Katie.`
10. `In one sentence, explain why leaves look green.`

## Timing points

Record in milliseconds where instrumentation permits:

- **T0** — wake detected
- **T1** — first microphone frame sent
- **T2** — endpoint/end-of-user-speech accepted by robot
- **T3** — usable/final transcript available
- **T4** — LLM request started
- **T5** — first LLM token/text chunk
- **T6** — first TTS request/text chunk
- **T7** — first TTS audio received by robot
- **T8** — first audio sample sent to speaker

Primary result: `T8 - T2`

This measures the silence the user actually experiences after finishing a sentence.

## Pass criteria

Alpha 1 is promising if:

- median `T8 - T2` improves materially over Beta;
- no repeated clipping of the start/end of speech;
- recognition remains usable for all ten English utterances;
- no random reboot, AFE starvation or audio queue failure appears during three consecutive test runs;
- the response begins playing before the whole answer has necessarily completed upstream when the selected providers support streaming.

## Results table

| # | Utterance | Beta T8-T2 ms | Alpha T8-T2 ms | Delta ms | Transcript OK | Audio clean | Notes |
|---|-----------|--------------:|----------------:|---------:|---------------|-------------|-------|
| 1 | What time is it? | | | | | | |
| 2 | Tell me a very short joke. | | | | | | |
| 3 | What is twelve times seven? | | | | | | endpoint proof turn above; T8 still required |
| 4 | Explain what DNS does in one sentence. | | | | | | |
| 5 | Who are you? | | | | | | |
| 6 | Give me three colours. | | | | | | |
| 7 | What does HTTP stand for? | | | | | | |
| 8 | Tell me one fact about the Moon. | | | | | | |
| 9 | Say hello to Katie. | | | | | | |
| 10 | In one sentence, explain why leaves look green. | | | | | | |

## Stop conditions

Stop the Alpha test and return to Beta if any of these occur repeatedly:

- uncontrolled servo movement;
- persistent audio feedback loop;
- repeated device reboot;
- microphone pipeline fails to recover after a turn;
- server attempts to write or execute arbitrary model-generated hardware coordinates;
- keys or personal memory appear in logs intended for Git.
