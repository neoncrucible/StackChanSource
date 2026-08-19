# Kadence 2.0 Alpha 1 — Latency Benchmark

## Rule

Compare the existing Kadence Beta path and the Xiaozhi-backed Alpha path using the **same room, microphone position, Wi-Fi, speaking distance and ten utterances**.

Do not add memory, MCP, new animations or personality changes until the baseline comparison is complete.

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
- **T2** — endpoint/end-of-user-speech detected
- **T3** — usable/final transcript available
- **T4** — LLM request started
- **T5** — first LLM token/text chunk
- **T6** — first TTS request/text chunk
- **T7** — first TTS audio received
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
| 3 | What is twelve times seven? | | | | | | |
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
