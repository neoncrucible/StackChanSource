# Kadence 2.0 Alpha 2 — Milestone 3 Benchmark Plan

Status: **DESIGN LOCKED / PRE-SMOKE IMPLEMENTATION**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Decision under test

Choose the Alpha 2 default server-side LLM from recorded evidence while preserving both providers as pre-boot fallback profiles.

The candidates are deliberately limited to:

- **Gemini 3.5 Flash-Lite** — current validated reference;
- **OpenAI GPT-5.6 Luna** — sole OpenAI contender for Alpha 2 because higher-cost GPT-5.6 tiers are outside the intended operating-cost envelope for Kadence's planned utility workload.

No other OpenAI model is part of Milestone 3.

## Fixed variables

The LLM is the only variable under comparison. Both candidates use:

- canonical Kadence identity v1;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- Windows Silero endpoint hold at 700 ms;
- existing final-flush and robot microphone/playback lifecycle;
- Edge TTS `en-GB-SoniaNeural`;
- `nomem`;
- `nointent`;
- existing Idle / Listening / Thinking robot states;
- frozen Alpha 1 transport and firmware behaviour.

Milestone 3 must not retune transport to improve either candidate's result.

## GPT-5.6 Luna baseline

The first Luna compatibility/speed baseline uses:

- model: `gpt-5.6-luna`;
- endpoint: OpenAI Chat Completions through the pinned Xiaozhi OpenAI adapter;
- streaming: enabled;
- reasoning effort: `none`;
- no sampling parameters unless compatibility testing proves they are required.

`none` is intentional: Kadence is a latency-sensitive spoken assistant and Milestone 3 measures whether Luna can beat or justify replacing the current Flash-Lite baseline. If Luna later needs more reasoning for a specific utility workload, that is a separate measured decision rather than silently changing the benchmark.

## Scoring

Weighted decision score:

| Measure | Weight |
| --- | ---: |
| Latency | 35% |
| Answer quality / factual accuracy | 25% |
| Canonical Kadence personality adherence | 15% |
| Spoken-answer concision | 10% |
| Instruction following | 10% |
| Cost per turn / practical operating cost | 5% |

A candidate cannot win purely on aggregate score if it has a blocking reliability defect, recurring API incompatibility, fabricated capabilities, or materially breaks the canonical personality contract.

## Test sequence

### Stage A — compatibility smoke

Before benchmarking:

1. select Luna as a pre-boot profile;
2. boot the normal Alpha 2 stack;
3. verify the pinned OpenAI Chat Completions adapter streams `gpt-5.6-luna` successfully;
4. verify canonical identity loads unchanged;
5. run 2–3 short spoken turns;
6. confirm there is no transport regression.

If compatibility fails, stop. Fix only the Alpha 2 LLM-provider/profile boundary and repeat the smoke before adding benchmark instrumentation.

### Stage B — server-side controlled benchmark

Instrument both LLM providers with equivalent timestamps and use the same prompt pack.

Measure where available:

- request sent → first model text;
- request sent → first sentence / TTS-ready text;
- full LLM completion duration;
- token usage and estimated cost where available.

Prompt categories:

- simple factual accuracy;
- arithmetic / deterministic answer;
- concise technical explanation;
- exact instruction following;
- ambiguity / refusal to invent unavailable information;
- practical advice;
- natural Kadence wit;
- concise multi-part response.

### Stage C — physical voice benchmark

Run a smaller matched set through the actual robot and retain the accepted Alpha 1 timing markers.

Measure where available:

- endpoint request timing;
- ASR completion after commit;
- LLM first useful output;
- first TTS-ready output;
- end of user speech → first audible reply.

Human speech variation is recorded but is not used to disguise LLM-side latency differences.

## Gate

Milestone 3 passes only when:

- both Gemini Flash-Lite and GPT-5.6 Luna can be selected before boot;
- both complete the same benchmark under the fixed variables above;
- results and scoring are recorded;
- one provider/model is explicitly chosen as the Alpha 2 default;
- the other remains a working pre-boot fallback;
- no Alpha 1 transport invariant was changed.

The Control Surface LLM selector remains optional quality-of-life work and is not required to clear this milestone.
