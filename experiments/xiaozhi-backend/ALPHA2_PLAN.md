# Kadence 2.0 Alpha 2 — Locked Plan

Status: **SCOPE LOCKED / IMPLEMENTATION ACTIVE / M7 CLOSED / M8 ACTIVE**

Date locked: **20 Aug 2026**  
Post-M5 provider amendment: **22 Aug 2026**  
M6 closed / M7 scope locked: **23 Aug 2026**  
M7 closed / M8 active: **23 Aug 2026**

Branch: `kadence/2.0-alpha-2`

Parent / frozen Alpha 1 head:

`2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`

Physically validated Alpha 1 firmware checkpoint:

`b51bd762eb315b7bc330db0a5f9ecc1daa2183da`

## Alpha 2 question

> Can Kadence become recognisably herself and genuinely useful, with Project-owned server-side intelligence boundaries and safe read-only utilities, without sacrificing Alpha 1's proven voice transport?

## User-visible goal

Kadence becomes a fast, useful desktop assistant with a canonical personality, short-session conversational continuity and tightly controlled read-only utilities while preserving the validated Alpha 1 transport and robot-side behaviour.

From M6 onward Alpha 2 deliberately uses **GPT-5.6 Luna only** for LLM inference. The earlier Gemini/Luna dual-provider work remains historical validation evidence, not an ongoing fallback requirement.

The intended beta/live cognition selector is **LOCAL / LUNA** only once a local engine exists. There is no automatic fallback or silent escalation contract: if the selected engine fails, the failure is surfaced rather than switching providers behind the user's back.

## Non-negotiable Alpha 1 transport invariants

Alpha 2 inherits and does not silently retune:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime `gpt-realtime-whisper` ASR path;
- Windows Silero preferred endpointing with **700 ms** sustained-silence hold;
- ESP32 AFE endpoint fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot authority over microphone stop, final flush and playback lifecycle;
- versioned `type: "kadence"` Project control messages;
- no raw model-generated servo coordinates;
- no API keys or personal memory committed to Git;
- `beta/project-kadence` remains the independent rollback line;
- `kadence/2.0-alpha-1` remains frozen history.

If an Alpha 2 feature unexpectedly requires changing one of these transport invariants, implementation stops and the scope is reviewed before proceeding.

## Personality / identity contract

Kadence's canonical personality is provider-independent and Project-owned.

Core character:

- cool, analytical and precise;
- competent before performative;
- sharp wit and playful sarcasm;
- humour used naturally rather than forced into every response;
- concise spoken answers by default;
- utility and factual clarity take priority over character performance;
- no generic assistant cheerleading or excessive friendliness;
- natural British English.

The canonical personality always loads by default.

M7 permits one temporary free-text behaviour overlay from the Control Surface. It is an overlay only: it never replaces the canonical identity, never persists across a backend restart and cannot override safety/tool/utility authority.

## Expressions and physical behaviour

Alpha 2 adds **no new expression system and no new LED behaviour**.

Existing robot states remain as already implemented:

- Idle
- Listening
- Thinking

M6's static weather icon is a bounded utility display result, not a model-controlled expression system.

No model-selected facial expression, LED expression, servo motion or arbitrary physical action is in Alpha 2 scope.

## LLM plan

### Historical M3 decision

M3 compared Gemini 3.5 Flash-Lite with GPT-5.6 Luna under the same canonical identity, ASR, endpointing and TTS. Gemini won raw provider latency; Luna won broader blind quality and physical conversational flow. Luna therefore became the accepted Alpha 2 default.

M5 subsequently proved that the Project-owned tool boundary could work through both providers, including a provider-local repair for Gemini 3 function-call continuation signatures. This completed the abstraction test; it did **not** create a requirement to carry two providers forever.

### Post-M5 simplification amendment

From M6 onward:

- Alpha 2 supports **Luna only** as its active cloud LLM;
- Gemini is retired from the Kadence runtime/configuration/control path;
- no further Gemini dual testing is required;
- no fallback model is configured;
- a Luna failure is allowed to fail visibly;
- historical M3/M5 Gemini evidence remains in validation records and Git history;
- dormant Gemini source inside the pinned third-party Xiaozhi checkout is not treated as an active Kadence capability and does not need to be deleted from upstream history.

Future beta/live target:

- `LOCAL` — explicit local inference mode;
- `LUNA` — explicit cloud inference mode.

There is **no AUTO mode**, no silent local-to-cloud escalation and no automatic cloud fallback in the accepted target architecture. Provider selection remains a conscious operator/user choice.

LOCAL is still outside Alpha 2 implementation scope. Alpha 2 must not fake a LOCAL switch before the local engine exists.

## Conversation continuity

Alpha 2 retains short live-session conversation context so follow-up questions across separate wake-word turns make sense.

This is **not persistent memory**.

- restart clears context;
- no durable personal profile;
- no vector database;
- no SD-card memory design in Alpha 2;
- no personal conversational content committed to Git.

## Utility scope

Alpha 2 establishes a Kadence-owned, explicit, schema-validated utility boundary.

Accepted M6 read-only utilities:

- date/time;
- weather;
- factual web lookup.

Unknown tools, malformed arguments and invented capabilities fail closed.

Out of scope for Alpha 2 utilities:

- generic unrestricted MCP access;
- arbitrary operating-system execution;
- email/calendar writes;
- PC control;
- smart-home writes;
- timers/reminders;
- robot motion.

## Milestones and gates

### Milestone 0 — Scope lock and branch provenance

- Lock this plan.
- Create `kadence/2.0-alpha-2` exactly from frozen Alpha 1 head `2d9ca4d...`.
- Preserve Alpha 1 and Beta rollback lines.

**Gate:** branch ancestry and rollback checkpoints verified.

**Status: PASS / CLOSED.**

### Milestone 1 — Canonical Kadence identity

Add one provider-independent canonical personality source while preserving Sonia voice and existing robot states.

**Gate:** factual, technical and conversational prompts show consistent Kadence identity without infrastructure leakage or forced character performance.

**Status: PASS / CLOSED.**

### Milestone 2 — Kadence Control Surface foundation

Windows EYE-themed operator surface with Start Server, Stop Server, server/robot state, health, warnings and useful live log output. It must not alter Alpha 1 transport behaviour.

**Status: USER ACCEPTED / CLOSED.**

### Milestone 3 — Gemini vs OpenAI benchmark

Historical provider comparison used to select the Alpha 2 default.

**Status: PASS / CLOSED.** GPT-5.6 Luna selected. Gemini's historical benchmark role is retained in the evidence, but Gemini was subsequently retired from active operation after M5.

### Milestone 4 — Session continuity

Add non-persistent conversational context across separate wake-word turns.

**Gate:** follow-up references work reliably and a backend restart demonstrably clears session context.

**Status: PASS / CLOSED.**

### Milestone 5 — Safe utility boundary

Implement and physically validate the allow-listed function/tool contract before enabling real utilities.

**Gate:** invalid/invented requests fail closed; allowed calls return structured results; ordinary conversation remains unaffected; tool turns coexist with M4 continuity.

**Status: PASS / CLOSED.** The boundary was physically proven with Luna and, for abstraction evidence, Gemini. Ongoing dual-provider testing is no longer required.

### Milestone 6 — First utilities

Enable time/date, weather and factual web lookup through the closed M5 boundary. Weather may emit only the trusted fixed-enum static pixel display result `clear | cloud | rain | snow`.

**Gate:** repeated physical tests mix ordinary conversation and read-only utility calls without fabricated results or infrastructure leakage. Alpha 2 M6 acceptance is Luna-only.

**Status: PASS / CLOSED.** Canonical record: `MILESTONE6_VALIDATION.md`. Final backend behaviour checkpoint before close-out: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`. Physically accepted pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`.

### Milestone 7 — Session behaviour overlay

M7 has exactly two operator states:

- **DEFAULT** — canonical Kadence, unchanged;
- **CUSTOM** — one free-text behaviour overlay supplied from the Control Surface.

Locked M7 behaviour:

- Custom text is applied only when the operator explicitly presses **Apply Custom**; typing alone never changes live behaviour.
- The canonical persona remains the authoritative base prompt.
- Custom text is appended as a clearly bounded behaviour preference and may alter delivery/style only.
- The overlay cannot override safety, tool schemas, utility authority, transport invariants or the canonical identity contract.
- Maximum custom text length: **1,000 characters**.
- Robot disconnect/reconnect does **not** clear the overlay while the same backend process remains alive.
- Pressing **DEFAULT** removes the overlay immediately.
- Stopping/restarting the backend clears the overlay and returns to DEFAULT.
- The Custom UI field is cleared on backend start/restart so stale text cannot imply an active overlay.
- No custom behaviour is written to config, Git, durable memory or persistent profile state.

**Gate:** prove canonical Default behaviour, obvious Custom behaviour, reconnect survival, immediate Default reset and backend-restart reset. Tool/safety rules must remain unchanged throughout.

**Status: PASS / CLOSED.** Canonical record: `MILESTONE7_VALIDATION.md`. Physically accepted M7 implementation checkpoint: `db4db895c4bf4ae6f39e360675a52ed7d185346f`. DEFAULT/CUSTOM switching, reconnect survival, immediate DEFAULT reset and backend-restart reset were physically accepted.

### Milestone 8 — Physical acceptance and Alpha 2 freeze

Run a mixed-use physical acceptance session covering normal conversation, personality, follow-ups, utility calls, deliberate utility failures and repeated wake/listen/reply/idle cycles.

**Gate:** record exact Luna model, persona revision, context behaviour, utility set, physical results and rollback SHA, then close Alpha 2 as `VALIDATED / FROZEN`.

## Explicitly out of scope for Alpha 2

- persistent/robot-owned memory;
- SD identity/memory architecture;
- continuous conversation or barge-in;
- new robot expressions or LED behaviour;
- model-driven physical motion;
- generic MCP access;
- timers/reminders;
- email/calendar/PC write control;
- smart-home write control;
- Pi 5 deployment;
- local LLM deployment;
- LOCAL/LUNA UI switching before a real local engine exists;
- AUTO routing or silent provider fallback;
- preset libraries or multiple named M7 personality modes;
- persistent custom behaviour profiles;
- Python migration unless independently required by a blocking defect;
- transport optimisation or endpoint retuning without new physical evidence.

## Immediate implementation priority

Proceed to **Milestone 8 — mixed physical acceptance, exact-state recording and Alpha 2 freeze**, preserving the closed M0-M7 behaviour and all frozen transport invariants unchanged.
