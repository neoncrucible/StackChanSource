# Kadence 2.0 Alpha 2 — Milestone 3 Stage A Validation

Status: **PASS — GPT-5.6 Luna compatibility and physical voice smoke**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Configuration under test

- LLM profile: `openai-luna`
- model: `gpt-5.6-luna`
- reasoning effort: `none`
- API path: pinned Xiaozhi OpenAI Chat Completions adapter, streaming enabled
- persona: canonical Kadence identity v1
- ASR: OpenAI Realtime `gpt-realtime-whisper`
- server endpoint: Silero 700 ms hold
- TTS: Edge `en-GB-SoniaNeural`
- memory: `nomem`
- intent: `nointent`
- transport/firmware: frozen Alpha 1 behaviour unchanged

## Compatibility result

The Alpha 2 Luna profile and compatibility patch loaded successfully, the pinned OpenAI provider initialized as `OpenAILLM`, the server bound normally, the robot connected, canonical identity loaded, and Realtime ASR announced the frozen 700 ms endpoint configuration.

An initial newline insertion defect in the Alpha 2 OpenAI compatibility patch was found during the first import smoke, repaired with a guarded migration, and the subsequent boot completed normally. This defect was confined to the new Alpha 2 LLM-provider patch boundary; no transport or firmware change was required.

## Physical voice smoke

Three exact spoken prompts were tested through the robot:

1. `Who are you?`
   - response: `I’m Kadence, your compact desktop robot assistant. Calm, capable, and only mildly judgmental about your life choices`
   - canonical identity/personality: pass
   - ASR final after commit: 0.515 s
   - endpoint request: 766 ms confirmed Silero silence

2. `What is twenty-three times seventeen?`
   - response: `391`
   - factual/deterministic correctness: pass
   - ASR final after commit: 0.610 s
   - endpoint request: 812 ms confirmed Silero silence

3. `Explain DNS in one sentence.`
   - response: `DNS translates human-friendly website names into the IP addresses computers use to find them`
   - technical accuracy and one-sentence instruction: pass
   - ASR final after commit: 0.500 s
   - endpoint request: 812 ms confirmed Silero silence

No model/configuration leakage, transport regression, TTS failure, or recurring provider error was observed in the smoke run.

## Decision

**Stage A passes.** GPT-5.6 Luna is compatible enough to enter the controlled Milestone 3 benchmark against Gemini 3.5 Flash-Lite.

This smoke does **not** select Luna as the Alpha 2 default. Stage B controlled provider measurements and Stage C matched physical voice measurements remain required before the Milestone 3 winner is chosen.
