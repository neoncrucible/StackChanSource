# Kadence 2.0 Alpha 2 — Milestone 3 Benchmark Plan

Status: **PASS / CLOSED — GPT-5.6 LUNA DEFAULT**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Progress

- Stage A compatibility smoke: **PASS** — see `MILESTONE3_STAGEA_VALIDATION.md`.
- Stage B controlled benchmark: **PASS** — clean zero-error confirmation plus locked blind quality review; see `MILESTONE3_STAGEB_VALIDATION.md` and `MILESTONE3_VALIDATION.md`.
- Stage C physical voice confirmation: **PASS** — corrected provider lock and retained physical evidence; see `MILESTONE3_VALIDATION.md`.
- Default-provider decision: **GPT-5.6 Luna selected**; Gemini 3.5 Flash-Lite retained as pre-boot fallback.

## Decision under test

Choose the Alpha 2 default server-side LLM from recorded evidence while preserving both providers as pre-boot fallback profiles.

The candidates are deliberately limited to:

- **Gemini 3.5 Flash-Lite** — current validated reference;
- **OpenAI GPT-5.6 Luna** — sole OpenAI contender for Alpha 2 because higher-cost GPT-5.6 tiers are outside the intended operating-cost envelope for Kadence's planned utility workload.

No other OpenAI model is part of Milestone 3.

**Final result:** GPT-5.6 Luna wins the combined benchmark and becomes the Alpha 2 default. Gemini remains available as the faster pre-boot fallback profile.

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

**Result: PASS on 21 Aug 2026.**

### Stage B — server-side controlled benchmark

Instrument both LLM providers with equivalent timestamps and use the same prompt pack.

The Stage B harness directly instantiates the actual pinned/runtime Gemini and OpenAI provider adapters with the same canonical Kadence persona and prompt. It does not start the robot/server transport. Provider call order is shuffled per repeat, each provider receives an equal discarded warm-up, and outputs are saved only below ignored `.runtime/benchmarks/`.

Measure where available:

- request sent → first model text;
- request sent → first sentence / TTS-ready text;
- full LLM completion duration;
- deterministic-answer checks;
- response length;
- token usage and estimated cost where available.

`first_tts_ready_ms` in Stage B is a provider-level speech-readiness proxy: the first streamed chunk that completes a punctuation boundary. Full Xiaozhi sentence handling and audible latency are measured separately in Stage C.

Prompt categories:

- simple factual accuracy;
- arithmetic / deterministic answer;
- concise technical explanation;
- exact instruction following;
- ambiguity / refusal to invent unavailable information;
- practical advice;
- natural Kadence wit;
- concise multi-part response.

The harness also generates a blind A/B quality-review document so subjective scoring can be completed without seeing provider identity or latency first.

**Result: PASS.** The clean confirmation completed 8/8 measured calls for each provider with zero errors. Gemini remained the raw latency winner; Luna won the locked blind human quality review 5 prompts to 1, with 2 ties.

### Stage C — physical voice benchmark

Run a smaller matched set through the actual robot and retain the accepted Alpha 1 timing markers.

Measure where available:

- endpoint request timing;
- ASR completion after commit;
- LLM first useful output;
- first TTS-ready output;
- end of user speech → first audible reply.

Human speech variation is recorded but is not used to disguise LLM-side latency differences.

**Result: PASS after harness correction.** The first blind harness attempt was rejected because ambient profile state could override the intended hidden mapping and the initial log-retention patch inherited V3 cleanup. After both harness defects were corrected, retained logs proved A=Gemini and B=Luna. The corrected matched physical confirmation showed frozen-transport timing remained stable; the human operator reported the model-side delay difference as negligible and gave B/Luna a slight audible-flow preference.

## Gate

Milestone 3 passes only when:

- both Gemini Flash-Lite and GPT-5.6 Luna can be selected before boot;
- both complete the same benchmark under the fixed variables above;
- results and scoring are recorded;
- one provider/model is explicitly chosen as the Alpha 2 default;
- the other remains a working pre-boot fallback;
- no Alpha 1 transport invariant was changed.

**Gate result: PASS.** GPT-5.6 Luna is the Alpha 2 default; Gemini 3.5 Flash-Lite remains the fallback; transport invariants remain unchanged.

The Control Surface LLM selector remains optional quality-of-life work and is not required to clear this milestone.
