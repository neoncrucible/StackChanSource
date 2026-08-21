# Project Kadence 2.0 - Alpha 2 Rolling Contingency Snapshot

**Status:** CURRENT THROUGH MILESTONE 3 / NEXT TARGET MILESTONE 4  
**Snapshot:** 21 Aug 2026, 23:37 Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Active branch:** `kadence/2.0-alpha-2`

## Purpose

This is the rolling recovery record for Project Kadence 2.0 Alpha 2. It is not a roadmap replacement. It exists so development can be resumed from a clean chat or recovered after a bad change without reopening already validated work.

## Proven anchors and rollback lines

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`.
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`.
- Independent rollback line: `beta/project-kadence`.
- Alpha 1 historical branch: `kadence/2.0-alpha-1`; it remains frozen and must not be rewritten or retuned casually.
- Pinned Xiaozhi upstream observed in accepted Alpha 2 boot: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`.
- Canonical Kadence persona SHA-256 observed at boot: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`.

## Frozen transport invariants inherited from Alpha 1

Do not silently retune any of the following during Alpha 2:

- Xiaozhi v1 bidirectional WebSocket transport.
- 16 kHz / 60 ms Opus robot uplink.
- OpenAI Realtime `gpt-realtime-whisper` ASR path.
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

Alpha 2 was branched from the frozen Alpha 1 head and rollback lines were preserved.

### M1 - Canonical Kadence identity: PHYSICALLY VALIDATED

Kadence's personality is Project-owned rather than provider-owned. Accepted character is cool, analytical, precise, competent first, concise in speech, naturally British, with sharp wit and playful sarcasm used sparingly. No new robot expression system or LED behaviour was added.

### M2 - Control Surface foundation: USER ACCEPTED / VALIDATED

Accepted Windows EYE-themed Control Surface provides start/stop controls, process and robot/server state, ASR/persona/model/transport status, preflight port checks, live UTF-8 logs, packaged EXE launching, project/Conda discovery, and narrow stale-Kadence cleanup. It delegates actual voice transport startup to the inherited frozen Alpha 1 path.

Evidence gap retained honestly: the final packaged STOP SERVER path is implemented, but a separately captured final packaged stop-cycle log was not recorded in the accepting chat.

### M3 - Gemini vs OpenAI benchmark: PASS / CLOSED

- Default LLM: GPT-5.6 Luna (`gpt-5.6-luna`, `reasoning_effort: none`).
- Fallback: Gemini 3.5 Flash-Lite.
- Selection remains pre-boot; changing provider requires server restart.
- Gemini won raw provider latency; Luna won overall blind quality and physical conversational flow.
- No Alpha 1 transport invariant was changed to favour either provider.

Accepted M3 caveats:

- Initial Stage C provider A/B harness was invalid because an ambient `KADENCE_LLM_PROFILE` could override the blind profile. This was corrected before accepting evidence.
- The Stage C log-retention issue was corrected before final evidence.
- One cold-boot session showed weaker wakeword pickup for roughly ten seconds after readiness; it resolved without retuning and is non-material unless reproduced consistently.

## Current Alpha 2 operating state

The normal development target is the packaged Control Surface starting the Alpha 2 Windows backend, with canonical Kadence identity loaded and Luna as default. Gemini remains the explicit fallback profile. Transport behaviour remains the frozen Alpha 1 behaviour.

Alpha 2 currently has no persistent personal memory, no vector database, no robot-owned memory, no arbitrary OS execution, no smart-home writes and no model-driven motion.

## NEXT: Milestone 4 - Non-persistent session continuity

### User-visible objective

Kadence should understand follow-up references across separate wake-word turns while the same backend session is alive.

Example acceptance sequence:

1. `Kadence, who wrote Dune?`
2. Kadence answers `Frank Herbert.`
3. New wake-word turn: `When was he born?`
4. Kadence resolves `he` to Frank Herbert and answers correctly.

### M4 implementation contract

- Retain short conversational context across separate wake-word turns.
- Context belongs to the running Kadence backend session, not to the robot and not to a provider-specific personality file.
- Restarting the backend must clear the context demonstrably.
- Do not introduce durable storage, a personal profile, vector retrieval, SD-card memory or long-term user memory.
- Keep the canonical persona as the base system identity on every turn.
- Keep the design as provider-independent as practical so Luna and later alternative inference engines are not the owners of Kadence's identity or session state.
- Do not add utilities, smart-home control, timers, PC control, expression work or transport optimisation under cover of M4.

### M4 gate

M4 passes only when physical testing demonstrates:

- correct pronoun/reference resolution across separate wake turns;
- at least one multi-step follow-up chain without losing the original subject;
- an unrelated new topic does not become contaminated by stale context;
- backend restart clears prior conversational context;
- canonical personality remains intact;
- normal wake/listen/reply/idle lifecycle remains stable;
- no frozen transport invariant changes.

## Remaining Alpha 2 roadmap after M4

- M5 - safe schema-validated, allow-listed utility boundary; invalid/invented calls fail closed.
- M6 - first read-only utilities: date/time, weather and factual web lookup.
- M7 - temporary session behaviour overlays from the Control Surface, always layered over canonical Kadence.
- M8 - mixed physical acceptance, exact-state recording and Alpha 2 freeze.

## Explicitly parked for post-Alpha-2

A promising future architecture was identified on 21 Aug 2026: Kadence should eventually support interchangeable cognition with `LOCAL / AUTO / LUNA` modes. The intended direction is that Kadence owns identity, session/memory policy and tools, while local or cloud models are replaceable inference engines. AUTO would eventually route routine/local work to a local model and escalate difficult reasoning to Luna.

This concept is deliberately NOT part of Alpha 2. Do not expand M4 to implement it. It is a candidate backbone for Alpha 3 or the first post-Alpha-2 architecture milestone after Alpha 2 is physically frozen.

## Recovery rules

If Alpha 2 becomes unstable:

1. Identify whether the regression is server-side Alpha 2 work or the frozen transport path.
2. Do not modify the frozen Alpha 1 branch to fix an Alpha 2 regression.
3. Compare against the Alpha 1 head `2d9ca4d...` and the accepted Alpha 2 milestone records.
4. Preserve the current Alpha 2 branch history; revert or repair forward rather than rewriting validated history unless there is a compelling reason.
5. Use `beta/project-kadence` only as the independent older rollback line when needed.
6. If physical evidence suggests an Alpha 1 transport invariant truly must change, stop and explicitly reopen that invariant before touching it.

## Resume instruction for a fresh chat

Read the live `kadence/2.0-alpha-2` branch, `ALPHA2_PLAN.md`, M1-M3 validation records and this rolling contingency snapshot. Treat M0-M3 as closed. Begin by discussing/inspecting the narrow M4 session-continuity implementation. Do not create a new branch, reopen provider benchmarking or retune transport unless new physical evidence requires it.
