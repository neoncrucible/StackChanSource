# Kadence 2.0 Alpha 2 — Milestone 3 Stage B Validation

Status: **PHYSICALLY RUN / PASS**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Scope

Stage B compared the two locked Milestone 3 candidates at the server provider boundary while keeping the canonical Kadence persona and benchmark prompt pack fixed:

- Gemini 3.5 Flash-Lite;
- OpenAI GPT-5.6 Luna with `reasoning_effort: none`.

Robot audio and transport were deliberately excluded from Stage B. They remain for Stage C.

## Clean confirmation run

Run ID: `20260821-183251`

Git head under test: `f58412e2a4545fc1cbfeca267e6b65b505528e65`

Configuration:

- 8 measured prompts per provider;
- 1 discarded warm-up per provider;
- same canonical persona;
- same prompt order set, with provider execution order shuffled;
- provider adapters loaded from the pinned Xiaozhi runtime;
- no robot audio / WebSocket transport involved.

Both providers completed **8/8 measured calls with zero errors** and both passed the two deterministic exact-output checks.

| Measure | Gemini 3.5 Flash-Lite | GPT-5.6 Luna |
| --- | ---: | ---: |
| first text median | 541.7 ms | 935.3 ms |
| first TTS-ready proxy median | 568.1 ms | 1018.0 ms |
| completion median | 583.9 ms | 1253.7 ms |
| measured calls | 8 | 8 |
| successful calls | 8 | 8 |
| errors | 0 | 0 |
| deterministic checks | 2/2 | 2/2 |

The provider-level speech-readiness penalty for Luna was therefore about **450 ms median** in the clean confirmation run.

## Blind quality review

The preceding two-repeat run generated a blind review with mapping hidden from the human reviewer until choices were locked.

Mapping after reveal:

- A = Gemini 3.5 Flash-Lite;
- B = GPT-5.6 Luna.

Human blind preferences across the eight prompts:

- Luna: **5 wins**;
- Gemini: **1 win**;
- Tie: **2**.

The review especially preferred Luna on technical personality, capability honesty, practical advice, and concise multipart explanation. Gemini retained the clear latency advantage.

One Gemini request in the earlier two-repeat run returned HTTP 429 because the benchmark exceeded the Gemini free-tier 15-requests-per-minute quota. This was treated as a benchmark/quota artefact rather than a provider reliability defect. The clean one-repeat confirmation stayed below that quota and completed with zero errors.

## Stage B decision

**PASS.**

Stage B established a real trade-off rather than a universal winner:

- Gemini is materially faster at the provider boundary;
- Luna won the blind human quality comparison;
- reliability and deterministic instruction following were equivalent in the clean confirmation run;
- Luna can become over-verbose on open-ended troubleshooting/personality prompts and this must be watched in physical voice use.

Proceed to **Stage C — blind physical voice A/B**. The decisive question is whether Luna's roughly 450 ms provider-level speech-readiness penalty is perceptible or objectionable once the complete Kadence voice pipeline is involved, and whether its quality/personality advantage survives spoken interaction.

No Alpha 1 transport invariant was changed for Stage B.
