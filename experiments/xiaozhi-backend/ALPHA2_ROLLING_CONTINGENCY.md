# Project Kadence 2.0 - Alpha 2 Rolling Contingency Snapshot

**Status:** CURRENT THROUGH MILESTONE 4 / MILESTONE 5 IMPLEMENTED — PHYSICAL VALIDATION PENDING  
**Snapshot:** 22 Aug 2026, 14:26 Europe/London  
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
- M4 implementation repair head before validation record: `063bb7a497ee1d179c1a0783a64cf287810edfca`.
- M4 closed recovery head before M5 implementation: `fb753073939359fda613adf2f5d7c9632dcf5281`.
- M5 implementation head before this snapshot update: `6880f52dca29101d0616f263094448888f2a7278`.

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

### M4 - Non-persistent session continuity: PASS / CLOSED

Kadence now owns short conversational continuity at backend-process scope rather than inside Luna, Gemini, the robot or Xiaozhi durable Memory.

Accepted architecture and limits:

- Project-owned `KadenceSessionHistory`.
- One volatile store owned at `WebSocketServer` process scope.
- History keyed by stable robot `device-id`.
- Fresh `ConnectionHandler` instances hydrate generic `user`/`assistant` history from the process store.
- Completed top-level spoken exchanges are committed back to the store.
- Both Luna and Gemini continue to consume the normal provider-neutral Xiaozhi `Dialogue` path.
- Maximum 8 completed exchanges.
- Secondary 12,000-character ceiling.
- Oldest complete exchange is pruned first.
- No TTL, summarisation, token-counting, durable storage, personal profile, vector database or SD-card memory.

Physical acceptance demonstrated:

- `Who wrote Dune?` followed by a separate wake `When was he born?` correctly resolved Frank Herbert.
- A multi-step Frank Herbert chain remained coherent through at least four connected turns.
- Switching to Tokyo cleanly displaced the old Dune topic, and `What is its population roughly?` resolved to Tokyo.
- Canonical Kadence personality remained intact.
- The retained count reached 8 and remained bounded at 8.
- A fresh WebSocket/ConnectionHandler hydrated `8 exchange(s)` and `Which is the biggest one?` correctly resolved the pre-reconnect Saturn context to Titan.
- The session test word `mongoose` was remembered before backend restart and forgotten after backend restart, with the new process beginning a fresh retained count.
- Normal wake/listen/endpoint/ASR/think/speak/idle behaviour remained functional and no frozen transport invariant changed.

M4 startup-history note:

- The first physical M4 boot failed closed on an overly brittle PowerShell handler-injection guard before backend launch.
- The guard was narrowed to an ASCII-only attachment point immediately before `handler.handle_connection(websocket)` without changing the M4 architecture.
- The corrected boot and full physical acceptance then passed.

M4 audio observation:

- One severe audible crackle was reported during the first post-reconnect Saturn/Titan answer.
- Server logs showed successful TTS generation with zero retries and no M4/session error for that answer.
- The event occurred shortly after WebSocket reconnect/resource handoff and did not recur during the remainder of the validation run.
- Treat as a non-blocking observation. Do not retune transport/playback for a single unreproduced event; investigate only if it becomes reproducible.

## Current Alpha 2 operating state

The normal development target is the packaged Control Surface starting the Alpha 2 Windows backend, with canonical Kadence identity loaded and Luna as default. Gemini remains the explicit fallback profile. Transport behaviour remains the frozen Alpha 1 behaviour.

Kadence now has bounded **volatile live-session conversational continuity** only. It still has no persistent personal memory, no vector database, no robot-owned memory, no arbitrary OS execution, no smart-home writes and no model-driven motion.

Backend restart intentionally clears M4 conversational continuity.

## CURRENT: Milestone 5 - Safe tool boundary

**Implementation status: BUILT / STATIC BOUNDARY TEST PASS / PHYSICAL VOICE VALIDATION PENDING.**

### User-visible objective

Introduce the first Project-owned boundary through which Kadence can request utilities later, without yet giving the model unrestricted capabilities or implementing M6 utilities under cover of M5.

### Accepted M5 architecture

Authority is deliberately separated from Xiaozhi's generic tool registry:

`provider proposes call -> Kadence allow-list/schema gate -> Project-owned handler -> structured result -> provider final wording`

The following architecture is explicitly rejected for Alpha 2:

`provider -> Xiaozhi generic plugin/MCP/IoT registry -> whatever executor happens to match`

The pinned Xiaozhi `UnifiedToolHandler` is therefore treated only as upstream plumbing/reference code and is bypassed whenever `KADENCE_TOOL_MODE` is active.

### Project-owned boundary

Tracked implementation:

- `experiments/xiaozhi-backend/kadence_tools.py`
- `experiments/xiaozhi-backend/kadence_tool_runtime.py`
- `experiments/xiaozhi-backend/apply_m5_tools_windows.ps1`
- `experiments/xiaozhi-backend/test_m5_tool_boundary.py`

Boundary properties:

- only explicitly registered Kadence tools are advertised;
- unknown/invented names fail closed;
- arguments may arrive as a JSON object or raw JSON string but must resolve to an object;
- required fields, types, enum values, bounds, patterns and nested shapes are checked before execution;
- every object schema must use `additionalProperties: false`;
- unsupported schema keywords fail registration rather than being silently ignored;
- synchronous and asynchronous handlers are supported;
- handler exceptions are contained and implementation details are not returned to the model;
- handler results must be JSON-safe and reject NaN/non-serialisable output;
- all outcomes use a small structured result envelope;
- there is no fallback to arbitrary Python, shell, filesystem, process, network, MCP, IoT or OS execution.

No new `jsonschema` dependency was introduced because the pinned runtime requirements do not declare it. The Project validator intentionally implements only the subset Alpha 2 needs and rejects schemas using unsupported constraints.

### Provider independence

Luna receives the generic OpenAI-style function descriptors directly.

The pinned Gemini adapter already converts the same generic `function.name / description / parameters` structure to Gemini `FunctionDeclaration`s. Because `google-generativeai==0.8.5` accepts a narrower schema dialect, the guarded M5 runtime patch sanitises **only Gemini's advertising copy** to common descriptive fields. The full Kadence schema remains unchanged and is still enforced before execution.

Provider compatibility therefore changes presentation only, never authority.

### M5 inert physical probe

Until M5 closes, the Alpha 2 launcher sets:

`KADENCE_TOOL_MODE=m5_probe`

The only registered executable capability is:

`kadence_boundary_probe`

It accepts one short safe `code` string and returns that code in a deterministic JSON result. It performs no network, filesystem, shell, process, device, home-automation or external action.

Kadence safe mode also suppresses Xiaozhi's synthetic `direct_answer` tool and generic function-call few-shot injection. Ordinary model text remains ordinary model text, preserving the existing M4 normal-conversation path. Only the Kadence registry's descriptors are advertised as executable tools.

### M4 coexistence

M5 does not modify M4's guarded completed-turn block, so the M4 patch remains recognisable/idempotent on later boots.

For real tool turns, M5 captures the original top-level user query, snapshots the dialogue immediately before the tool-result recursive model call, and after the final assistant response commits the new final user/assistant exchange back through the existing M4 `KadenceSessionHistory`. This is intended to make future utility turns survive normal WebSocket/handler churn without introducing durable memory.

### Static boundary evidence

The tracked `test_m5_tool_boundary.py` completed **29/29 checks** successfully before physical rollout. Covered cases include:

- valid allow-listed dict call;
- valid JSON-string call;
- invented tool;
- malformed JSON;
- non-object arguments;
- missing required field;
- wrong type;
- enum violation;
- numeric bound violation;
- unexpected extra field;
- internal-looking collision field;
- async handler;
- handler exception containment/no detail leak;
- non-JSON handler result;
- NaN result;
- empty registry advertising no capabilities;
- unregistered future weather utility refusing execution;
- duplicate registration;
- unsupported schema keyword;
- open-ended `additionalProperties: true` schema.

### M5 physical gate still required

Do **not** close M5 until the actual robot/backend path demonstrates:

- clean guarded startup with only `kadence_boundary_probe` in the safe allow-list;
- ordinary no-tool conversation still works normally;
- ordinary M4 follow-up continuity still works with function-call capability enabled;
- explicit spoken M5 probe causes the allow-listed tool to execute and returns a natural spoken result;
- a request for a non-allow-listed capability cannot produce arbitrary execution;
- a tool-using exchange survives a normal WebSocket reconnect via M4 process continuity;
- backend restart still clears session continuity;
- safe handler cleanup introduces no disconnect error;
- canonical personality remains intact;
- frozen transport behaviour remains stable;
- no unexplained recurring audio regression appears.

Only after those checks pass should `MILESTONE5_VALIDATION.md` be added and the milestone marked CLOSED.

## Remaining Alpha 2 roadmap after M5

- M6 - first read-only utilities: date/time, weather and factual web lookup.
- M7 - temporary session behaviour overlays from the Control Surface, always layered over canonical Kadence.
- M8 - mixed physical acceptance, exact-state recording and Alpha 2 freeze.

## Explicitly parked for post-Alpha-2

A promising future architecture was identified on 21 Aug 2026: Kadence should eventually support interchangeable cognition with `LOCAL / AUTO / LUNA` modes. The intended direction is that Kadence owns identity, session/memory policy and tools, while local or cloud models are replaceable inference engines. AUTO would eventually route routine/local work to a local model and escalate difficult reasoning to Luna.

This concept is deliberately NOT part of Alpha 2. Do not expand M5 to implement it. It is a candidate backbone for Alpha 3 or the first post-Alpha-2 architecture milestone after Alpha 2 is physically frozen.

## Recovery rules

If Alpha 2 becomes unstable:

1. Identify whether the regression is server-side Alpha 2 work or the frozen transport path.
2. Do not modify the frozen Alpha 1 branch to fix an Alpha 2 regression.
3. Compare against the Alpha 1 head `2d9ca4d...` and the accepted Alpha 2 milestone records.
4. Preserve the current Alpha 2 branch history; revert or repair forward rather than rewriting validated history unless there is a compelling reason.
5. Use `beta/project-kadence` only as the independent older rollback line when needed.
6. If physical evidence suggests an Alpha 1 transport invariant truly must change, stop and explicitly reopen that invariant before touching it.

## Resume instruction for a fresh chat

Read the live `kadence/2.0-alpha-2` branch, `ALPHA2_PLAN.md`, M1-M4 validation records and this rolling contingency snapshot. Treat M0-M4 as closed. Treat M5 as implemented but **not closed** until its physical voice/containment gate passes. Do not create another branch, reopen provider benchmarking, enable M6 utilities early, expose generic MCP/plugin/IoT execution, or retune transport unless new physical evidence requires it.
