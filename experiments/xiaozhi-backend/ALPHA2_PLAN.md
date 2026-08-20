# Kadence 2.0 Alpha 2 — Locked Plan

Status: **SCOPE LOCKED / IMPLEMENTATION ACTIVE**

Date locked: **20 Aug 2026**

Branch: `kadence/2.0-alpha-2`

Parent / frozen Alpha 1 head:

`2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`

Physically validated Alpha 1 firmware checkpoint:

`b51bd762eb315b7bc330db0a5f9ecc1daa2183da`

## Alpha 2 question

> Can Kadence become recognisably herself and genuinely useful, with interchangeable server-side intelligence and safe read-only utilities, without sacrificing Alpha 1's proven voice transport?

## User-visible goal

Kadence becomes a fast, useful desktop assistant with a canonical personality, short-session conversational continuity, selectable pre-boot LLM profiles and tightly controlled read-only utilities, while preserving the validated Alpha 1 transport and robot-side behaviour.

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

Future session behaviour modifiers may temporarily alter delivery (for example concise, technical, deadpan or creative modes), but they are overlays only. They do not replace the canonical personality, do not persist by default and cannot override safety or utility contracts.

## Expressions and physical behaviour

Alpha 2 adds **no new expression system and no new LED behaviour**.

Existing robot states remain as already implemented:

- Idle
- Listening
- Thinking

No model-selected facial expression, LED expression, servo motion or arbitrary physical action is in Alpha 2 scope.

## LLM plan

LLM selection is server-side and occurs **before server boot**.

Expected operator flow:

1. Open Kadence Control Surface.
2. Select provider/model profile.
3. Optionally choose a temporary session behaviour modifier.
4. Start the server.
5. Validate server health.
6. Boot/connect Kadence.

The selected LLM remains fixed for that server run. Changing LLM requires server shutdown and restart. There is no Alpha 2 live hot-swap requirement.

Gemini Flash-Lite is the Alpha 1 reference candidate. OpenAI will be added as a competing Alpha 2 candidate. Both are benchmarked using the same canonical Kadence personality, ASR, endpointing and TTS. The benchmark winner becomes the default; both remain selectable as fallback profiles.

## Conversation continuity

Alpha 2 may retain short live-session conversation context so follow-up questions across separate wake-word turns make sense.

This is **not persistent memory**.

- restart clears context;
- no durable personal profile;
- no vector database;
- no SD-card memory design in Alpha 2;
- no personal conversational content committed to Git.

## Utility scope

Alpha 2 establishes a Kadence-owned, explicit, schema-validated utility boundary.

Initial read-only utilities:

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

### Milestone 1 — Canonical Kadence identity

- Add one provider-independent canonical personality source.
- Make server runtime consume the canonical identity without burying identity ownership inside a provider-specific profile.
- Preserve Sonia voice and existing robot states.

**Gate:** scripted factual, technical and conversational prompts show consistent Kadence identity without infrastructure leakage or forced character performance.

### Milestone 2 — Kadence Control Surface foundation

Rebuild the Windows server monitor as an EYE-themed Kadence boot console and live monitor.

Pre-boot controls/status should support:

- selected LLM provider/model;
- canonical identity status;
- optional temporary session modifier;
- Sonia voice status;
- configured utility status;
- server configuration/API-key-presence health without displaying secrets;
- Start Server / Stop Server.

Once the server is running, boot configuration controls lock and the UI becomes a live monitor showing useful operational state such as:

- Kadence/server connection state;
- current provider/model;
- live turn transcript where available;
- pipeline timings where available;
- utility/tool activity;
- warnings/errors;
- access to detailed logs.

The EYE avatar is the visual centrepiece and may reflect **monitor/system state**, but this does not add or alter robot-side expression behaviour.

**Gate:** the Control Surface starts/stops the existing backend cleanly and accurately reports state without changing Alpha 1 transport behaviour.

### Milestone 3 — Gemini vs OpenAI benchmark

Hold all non-LLM variables constant and compare Gemini Flash-Lite with the chosen OpenAI candidate.

Measure at minimum:

- LLM request to first useful output;
- LLM request to first TTS-ready output where measurable;
- end-of-user-speech to audible reply where measurable;
- answer quality/accuracy;
- canonical personality adherence;
- spoken-answer concision;
- instruction following;
- cost per turn where practical.

**Gate:** choose the Alpha 2 default from recorded benchmark evidence while retaining both pre-boot profiles.

### Milestone 4 — Session continuity

Add non-persistent conversational context across separate wake-word turns.

**Gate:** follow-up references work reliably and a backend restart demonstrably clears the session context.

### Milestone 5 — Safe utility boundary

Implement the validated, allow-listed function/tool contract before enabling real utility actions.

**Gate:** invalid or invented tool requests fail closed; allowed calls return structured results; ordinary conversation remains unaffected when no tool is needed.

### Milestone 6 — First utilities

Enable time/date, weather and factual web lookup.

**Gate:** repeated physical tests mix ordinary conversation and read-only utility calls without fabricated results or infrastructure leakage.

### Milestone 7 — Session behaviour overlays

Allow optional temporary behaviour modifiers from the Control Surface while canonical Kadence always remains the base identity.

**Gate:** disabling the modifier returns behaviour to canonical defaults and modifiers cannot override safety/tool rules.

### Milestone 8 — Physical acceptance and Alpha 2 freeze

Run a mixed-use physical acceptance session covering normal conversation, personality, follow-ups, utility calls, deliberate utility failures and repeated wake/listen/reply/idle cycles.

**Gate:** record exact provider/model, persona revision, context behaviour, utility set, physical results and rollback SHA, then close Alpha 2 as `VALIDATED / FROZEN`.

## Explicitly out of scope for Alpha 2

- persistent/robot-owned memory;
- SD identity/memory architecture;
- continuous conversation or barge-in;
- new robot expressions or LED behaviour;
- model-driven physical motion;
- generic MCP access;
- timers/reminders;
- email/calendar/PC write control;
- Pi 5 deployment;
- Python migration unless independently required by a blocking defect;
- transport optimisation or endpoint retuning without new physical evidence.

## Immediate implementation priority

The first implementation target is to complete **Milestone 1 (Canonical Kadence identity)** and **Milestone 2 (Kadence Control Surface foundation)** while leaving the frozen transport untouched.
