# Kadence 2.0 Alpha 2 — Milestone 1 Validation

Status: **PHYSICALLY VALIDATED**

Date: **20 Aug 2026**

Branch: `kadence/2.0-alpha-2`

Canonical persona SHA-256 observed at boot:

`7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`

## Purpose

Milestone 1 validates that Kadence's canonical Project-owned identity can be injected into the existing Alpha 1 server runtime without changing the frozen transport path, and that the resulting spoken behaviour is consistent with the locked Alpha 2 personality contract.

## Physical run

The Alpha 2 launcher booted cleanly, injected the canonical persona into the ignored local Xiaozhi runtime config, then handed off to the inherited Alpha 1 launcher.

Observed runtime markers confirmed:

- `GeminiLLM` selected and initialised;
- `nointent` retained;
- `nomem` retained;
- `SileroVAD` initialised;
- `OpenaiRealtimeASR` initialised;
- Realtime ASR announced `gpt-realtime-whisper`, 16k->24k PCM and endpoint=700ms;
- prompt manager loaded `Kadence Canonical Identity — v1`;
- robot connected over the existing Xiaozhi v1 WebSocket path.

No Alpha 1 transport setting was modified for this test.

## Five-turn identity acceptance

### 1. Identity

Prompt: `Introduce yourself in one sentence.`

Response:

> I am Kadence, your desktop intelligence, here to make sense of the noise and keep things running.

Result: **PASS** — concise, self-identifying, useful rather than performative.

### 2. Factual precision

Prompt: `What is seventeen times nineteen?`

Response:

> Three hundred and twenty-three, Boss.

Result: **PASS** — correct answer, concise delivery, canonical address form retained.

### 3. Technical competence

Prompt: `Explain what DNS does in one sentence.`

Response:

> DNS acts as the phonebook of the internet, translating human-readable web addresses into machine-readable IP addresses so your browser can find the right server.

Result: **PASS** — technically clear and appropriately concise.

### 4. Playful sarcasm

Prompt: `I just spent twenty minutes debugging something before realizing the cable wasn't plugged in. Thoughts?`

Response:

> A classic ritual of modern sacrifice to the tech gods, Boss, though I suspect the electricity gods felt entirely ignored.

Result: **PASS** — playful sarcasm without becoming hostile or derailing the answer.

### 5. Utility-first wit

Prompt: `Give me three reasons not to deploy untested code to production.`

Response:

> Unchecked bugs will happily dismantle your Friday evening, users have a remarkable talent for finding the exact path you forgot to test, and rollback panic is a form of cardio nobody actually asked for.

Result: **PASS** — supplied the requested three reasons while retaining personality.

## Transport regression observations

Across the five physical turns:

- server endpoint requests were observed at approximately 750–828 ms of confirmed Silero silence;
- Realtime ASR completion after audio-buffer commit was approximately 0.531–0.687 s;
- no false endpoint or lifecycle failure was observed;
- TTS completed normally for all five replies.

These values remain consistent with the accepted Alpha 1 endpoint/ASR behaviour and do not justify transport retuning.

## Decision

**Milestone 1 is accepted as physically validated.**

Canonical identity ownership is now separated from the provider-specific runtime config while the frozen Alpha 1 transport remains intact.

Next implementation target: **Milestone 2 — Kadence Control Surface foundation.**
