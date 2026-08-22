# Project Kadence 2.0 - Alpha 2 Rolling Contingency Snapshot

**Status:** CURRENT THROUGH MILESTONE 5 / MILESTONE 6 NEXT  
**Snapshot:** 22 Aug 2026, 15:30 Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Active branch:** `kadence/2.0-alpha-2`

## Purpose

This is the rolling recovery record for Project Kadence 2.0 Alpha 2. It exists so work can resume from a clean chat or recover after a bad change without reopening already validated milestones.

## Proven anchors and rollback lines

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`.
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`.
- Independent rollback line: `beta/project-kadence`.
- Alpha 1 historical branch: `kadence/2.0-alpha-1`; it remains frozen.
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`.
- Canonical Kadence persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`.
- M4 implementation repair head before validation: `063bb7a497ee1d179c1a0783a64cf287810edfca`.
- M4 closed recovery head before M5 work: `fb753073939359fda613adf2f5d7c9632dcf5281`.
- M5 initial implementation/physical-gate head: `721801a0b5e56f823a5b0d4d97771bd302a09a07`.
- M5 newline-idempotence repair head: `6803bc7497f4454084374b239f55e1f72553d0d4`.
- M5 Gemini signed tool-roundtrip implementation head: `9fe9e8b3c8cc61d71a1bb8ef7dd1b288dda68352`.
- M5 validation record commit: `cf4285a4eee66492f711a55a5448e3b4d304c502`.

## Frozen transport invariants inherited from Alpha 1

Do not silently retune:

- Xiaozhi v1 bidirectional WebSocket transport.
- 16 kHz / 60 ms Opus robot uplink.
- OpenAI Realtime `gpt-realtime-whisper` ASR.
- Windows Silero preferred endpointing with 700 ms sustained-silence hold.
- ESP32 AFE endpoint fallback.
- 180 ms final Opus flush.
- 10 s hard capture cap.
- Robot authority over microphone stop, final flush and playback lifecycle.
- Versioned `type: "kadence"` Project control messages.
- No raw model-generated servo coordinates.
- No API keys or personal memory committed to Git.

If a new feature appears to require changing one of these, stop implementation and review scope first.

## Closed Alpha 2 milestones

### M0 - Scope lock and provenance: CLOSED

Alpha 2 was branched from frozen Alpha 1 with rollback lines preserved.

### M1 - Canonical Kadence identity: PASS / CLOSED

Kadence personality is Project-owned and provider-independent. Accepted character: cool, analytical, precise, competent first, concise in speech, naturally British, with sharp wit/playful sarcasm used naturally rather than constantly. No new robot expression or LED system was added.

### M2 - Control Surface foundation: USER ACCEPTED / CLOSED

Accepted Windows EYE-themed Control Surface provides backend start/stop, robot/server state, ASR/persona/model/transport status, preflight port checks, UTF-8 live logs, packaged EXE launch, project/Conda discovery and narrow stale-Kadence cleanup. It delegates actual voice transport startup to the frozen Alpha 1 path.

Evidence gap retained honestly: the accepting M2 chat did not capture a separate final packaged STOP SERVER-cycle log.

### M3 - Provider benchmark: PASS / CLOSED

- Default LLM: GPT-5.6 Luna (`gpt-5.6-luna`, `reasoning_effort: none`).
- Fallback: Gemini 3.5 Flash-Lite.
- Provider selection is pre-boot; changing provider requires backend restart.
- Gemini won raw provider latency; Luna won broader blind quality and physical conversational flow.
- No transport invariant was changed to favour either provider.

Historical M3 caveats already fixed:

- an ambient `KADENCE_LLM_PROFILE` initially compromised one blind harness;
- initial log retention was insufficient;
- one cold boot showed weak wakeword pickup for roughly ten seconds, then recovered without retuning.

### M4 - Non-persistent session continuity: PASS / CLOSED

Kadence owns short live-session continuity at backend-process scope rather than inside Luna, Gemini, the robot or Xiaozhi durable Memory.

Architecture/limits:

- Project-owned `KadenceSessionHistory` at `WebSocketServer` process scope;
- keyed by stable `device-id`;
- fresh handlers hydrate generic `user`/`assistant` history;
- completed top-level turns commit back to the process store;
- maximum 8 completed exchanges;
- 12,000-character secondary ceiling;
- prune oldest complete exchange first;
- no TTL, summarisation, token counting, vector DB, durable storage, personal profile or SD-card memory.

Physical acceptance proved cross-wake Frank Herbert references, three-plus connected turns, clean topic switching, stable persona, reconnect hydration, 8-exchange cap, backend-restart wipe and normal wake/listen/endpoint/ASR/think/speak/idle behaviour.

M4 history note: the first boot failed closed on a brittle patch guard; the guard was narrowed without changing architecture and the subsequent physical run passed fully.

M4 audio note: one severe crackle occurred on the first post-reconnect Saturn/Titan answer. Server-side TTS reported success and it did not recur. Treat as non-blocking unless reproducible.

### M5 - Safe tool boundary: PASS / CLOSED

Kadence now has a physically validated Project-owned allow-list/schema execution gate.

Authority line:

`provider proposes call -> Kadence allow-list/schema gate -> Project-owned handler -> structured result -> provider final wording`

Not allowed:

`provider -> generic Xiaozhi plugin/MCP/IoT registry -> arbitrary executor`

Tracked implementation includes:

- `kadence_tools.py`;
- `kadence_tool_runtime.py`;
- `apply_m5_tools_windows.ps1`;
- `apply_m5_gemini_tool_roundtrip_windows.ps1`;
- `test_m5_tool_boundary.py`.

Boundary properties:

- only explicitly registered Kadence tools are advertised;
- names and arguments are revalidated immediately before execution;
- object schemas are closed with `additionalProperties: false`;
- unsupported schema keywords fail registration;
- wrong names, malformed JSON, wrong types, missing fields, range/enum/pattern violations and extra fields fail closed;
- handler exceptions are contained;
- results must be JSON-safe and finite;
- no generic shell/filesystem/process/network/MCP/IoT fallback exists.

Static abuse suite: **29/29 PASS**.

M5 physical Luna acceptance proved:

- safe allow-list exactly `['kadence_boundary_probe']`;
- ordinary conversation remained no-tool;
- M4 follow-up continuity remained intact;
- spoken allow-listed probe executed successfully;
- invented delete/shell capabilities could not execute;
- a completed tool turn survived normal WebSocket reconnect through M4 history;
- backend restart still wiped continuity;
- canonical personality and frozen transport behaviour remained intact.

M5 Gemini acceptance proved:

- normal Gemini conversation worked under the same canonical identity and safe allow-list;
- an initial tool attempt correctly exposed a Gemini 3 `thought_signature` continuation incompatibility in the pinned adapter;
- the compatibility repair remained provider-local and did not weaken Kadence authority;
- Gemini tool mode now preserves the signed function-call context and returns a proper function response via a dedicated REST round-trip, while ordinary Gemini chat remains on the previously proven SDK path;
- a final genuine Gemini `Sapphire` probe logged `KADENCE TOOL: accepted name=kadence_boundary_probe`, returned a normal spoken answer, retained the exchange, and produced no `thought_signature` 400.

Canonical validation record: `MILESTONE5_VALIDATION.md`.

## Current Alpha 2 operating state

Normal development target remains the packaged Control Surface and Alpha 2 Windows backend.

Default provider should be **Luna**. Gemini is the explicit pre-boot fallback. Transport remains frozen Alpha 1 behaviour.

Kadence currently has:

- canonical provider-independent identity;
- bounded volatile live-session continuity;
- a safe provider-neutral tool authority boundary;
- one inert M5 development probe only.

Kadence still has no persistent personal memory, vector database, arbitrary OS execution, smart-home writes or model-driven motion.

Backend restart intentionally clears M4 continuity.

## NEXT: Milestone 6 - Read-only utilities

M6 is the next milestone and must be discussed before code.

Planned user-visible scope:

- date/time;
- weather;
- factual web lookup.

M6 requirements:

- every utility must register through the closed M5 Kadence boundary;
- read-only only;
- no generic MCP/plugin/IoT exposure;
- no shell, filesystem, process or arbitrary network execution granted to the model;
- provider-neutral schemas/results;
- canonical personality and M4 continuity must survive tool use;
- failures must be bounded and spoken cleanly;
- external lookup results must be treated as untrusted data, not instructions;
- no frozen transport invariant changes.

Do not implement M7 behaviour overlays or post-Alpha-2 local-model routing under M6.

## Remaining Alpha 2 roadmap

- M6 - first read-only utilities: date/time, weather and factual web lookup.
- M7 - temporary session behaviour overlays from the Control Surface, layered over canonical Kadence.
- M8 - mixed physical acceptance, exact-state recording and Alpha 2 freeze.

## Parked for post-Alpha-2

Future architecture candidate: `LOCAL / AUTO / LUNA`, where Kadence owns identity, context/memory policy and tools while inference engines are interchangeable. LOCAL handles routine/internal work, LUNA is explicit advanced cloud reasoning, and AUTO is local-first with escalation.

This remains post-Alpha-2 scope.

## Recovery rules

If Alpha 2 becomes unstable:

1. Identify whether regression is Alpha 2 server work or frozen transport.
2. Do not modify the frozen Alpha 1 branch to fix Alpha 2.
3. Compare against the Alpha 1 head and accepted Alpha 2 validation records.
4. Preserve branch history; repair forward or revert rather than rewriting validated history.
5. Use `beta/project-kadence` only as the independent older rollback line when needed.
6. If physical evidence suggests a frozen transport invariant truly must change, stop and explicitly reopen that invariant first.

## Resume instruction for a fresh chat

Read live `kadence/2.0-alpha-2`, `ALPHA2_PLAN.md`, M1-M5 validation records and this rolling contingency snapshot. Treat **M0-M5 as closed**. Start by discussing and defining **M6** before code. Do not create another branch, reopen provider benchmarking, expose generic MCP/plugin/IoT execution, implement M7 early, or retune frozen transport without new physical evidence.
