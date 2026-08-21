# Kadence 2.0 Alpha 2 — Milestone 3 Validation

Status: **PASS — GPT-5.6 Luna selected as Alpha 2 default**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Decision

Milestone 3 selects **OpenAI GPT-5.6 Luna** (`gpt-5.6-luna`, `reasoning_effort: none`) as the Alpha 2 default server-side LLM.

**Gemini 3.5 Flash-Lite remains supported as the pre-boot fallback profile.**

The decision is based on the combined Stage A compatibility smoke, Stage B controlled provider benchmark and corrected Stage C physical confirmation. No Alpha 1 transport invariant was retuned to favour either provider.

## Stage A — compatibility

Luna passed the physical compatibility smoke through the normal Alpha 2 stack:

- OpenAI Chat Completions provider initialised and streamed successfully;
- canonical Kadence identity loaded unchanged;
- spoken arithmetic and technical answers were correct;
- no transport regression or provider/infrastructure leakage was observed.

## Stage B — controlled provider benchmark

Both providers were exercised through the real pinned/runtime provider adapters with the same canonical persona and prompt pack.

Clean confirmation run:

| Metric | Gemini 3.5 Flash-Lite | GPT-5.6 Luna |
| --- | ---: | ---: |
| Successful measured calls | 8 / 8 | 8 / 8 |
| Errors | 0 | 0 |
| First text median | 541.7 ms | 935.3 ms |
| First TTS-ready median | 568.1 ms | 1018.0 ms |
| Completion median | 583.9 ms | 1253.7 ms |
| Deterministic auto-checks | 2 / 2 | 2 / 2 |

The earlier 16-call Gemini run hit the documented free-tier request-per-minute quota on the final call; the reduced clean confirmation run completed with zero errors and confirmed that this was a benchmark-rate-limit event rather than a provider reliability defect.

### Blind human quality result

The first Stage B blind review mapped **A = Gemini** and **B = Luna** only after the human choices were locked.

Human preference across the eight prompts:

- Luna: **5 wins**
- Gemini: **1 win**
- Ties: **2**

Luna was preferred for natural language, capability honesty, practical usefulness and Kadence personality. Gemini was materially faster and sometimes delivered the sharper single-line quip. Luna's main observed weakness was occasional over-expansion on troubleshooting/personality prompts, to be addressed through later persona refinement rather than benchmark-specific provider tuning.

## Stage C — physical voice confirmation

### Harness correction

The first Stage C A/B attempt was invalid for provider comparison because an ambient `KADENCE_LLM_PROFILE` environment override could take precedence over the local blind profile file. In addition, the initial evidence-capture patch redirected the ordinary Control Surface backend log into the Stage C run folder but inherited V3's exit cleanup, which deleted that evidence file when the UI closed.

Both defects were corrected before accepting Stage C evidence:

- the Stage C harness now passes the hidden mapped profile explicitly to the Alpha 2 launcher, taking precedence over ambient profile state;
- Stage C raw backend logs are retained on Control Surface exit.

No transport, endpointing, ASR, TTS or firmware behaviour was changed by those fixes.

### Corrected physical confirmation

Corrected mapping and startup evidence confirmed:

- **A = Gemini 3.5 Flash-Lite** and runtime initialised `GeminiLLM`;
- **B = GPT-5.6 Luna** and runtime initialised `OpenAILLM` with `gpt-5.6-luna`, `reasoning_effort: none`.

A matched two-prompt recovery set was used after the harness correction:

1. `What is forty-six times nineteen? Reply with only the number.`
2. `Explain what a VPN does in one sentence.`

Both providers returned the correct arithmetic answer (`874`) and usable one-sentence VPN explanations.

Observed frozen-transport timing remained consistent:

| Physical marker | Gemini | Luna |
| --- | --- | --- |
| Endpoint request | 828 ms / 719 ms | 703 ms / 828 ms |
| ASR completion after commit | 0.500 s / 0.594 s | 0.531 s / 0.485 s |

The human operator reported that the physical latency difference was negligible in use. On the corrected blind run, the answers were very similar, but **B flowed slightly better audibly**. After reveal, B was Luna.

The corrected Stage C was deliberately used as physical latency/flow confirmation rather than rerunning the full Stage B quality pack through speech. Stage B remains the broader controlled quality evidence.

### Wakeword note

A short period of weaker wakeword pickup was observed immediately after cold boot during one Stage C session. Waiting roughly ten seconds after robot/server readiness resolved the behaviour and it was judged non-material for normal use. No wakeword, AFE, endpointing or transport setting was changed.

## Milestone 3 conclusion

Gemini is the clear raw provider-latency winner. Luna is the stronger overall Kadence model on blind quality and physical conversational feel, while its additional provider latency was not materially noticeable in normal physical use.

Therefore:

- **Default:** GPT-5.6 Luna
- **Fallback:** Gemini 3.5 Flash-Lite
- **Luna reasoning effort:** `none`
- **Provider selection:** pre-boot only; changing provider still requires server restart
- **Transport:** unchanged from frozen Alpha 1

## Follow-up

Persona refinement may make Luna's wit sharper and shorter, but that work happens after the Milestone 3 benchmark is closed so the benchmark evidence remains uncontaminated.

Next milestone: **Milestone 4 — non-persistent session continuity.**
