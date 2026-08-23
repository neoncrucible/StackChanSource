# Project Kadence 2.0 - Alpha 2 Rolling Contingency Snapshot

**Status:** CURRENT THROUGH MILESTONE 6 / M7 SCOPE LOCKED / IMPLEMENTATION ACTIVE  
**Snapshot:** 23 Aug 2026, Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Active branch:** `kadence/2.0-alpha-2`

## Purpose

This is the rolling recovery record for Project Kadence 2.0 Alpha 2. It exists so work can resume from a clean chat or recover after a bad change without reopening already validated milestones or resurrecting retired architecture.

## Proven anchors and rollback lines

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`.
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`.
- Independent rollback line: `beta/project-kadence`.
- Alpha 1 historical branch: `kadence/2.0-alpha-1`; it remains frozen.
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`.
- Canonical Kadence persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`.
- M4 implementation repair head before validation: `063bb7a497ee1d179c1a0783a64cf287810edfca`.
- M4 closed recovery head before M5: `fb753073939359fda613adf2f5d7c9632dcf5281`.
- M5 initial physical-gate head: `721801a0b5e56f823a5b0d4d97771bd302a09a07`.
- M5 newline-idempotence repair: `6803bc7497f4454084374b239f55e1f72553d0d4`.
- M5 Gemini signed tool-roundtrip implementation: `9fe9e8b3c8cc61d71a1bb8ef7dd1b288dda68352`.
- M5 closed recovery head before provider simplification: `11a7d0f6c59985a62f8e7f7618b82114c9fcef66`.
- Post-M5 provider simplification work began at `7735ccdec5d0174c0824c139e1a1666ee71ab35d`.
- M6 physically accepted pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`.
- M6 final backend behaviour checkpoint before close-out: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`.
- M6 canonical validation record: `MILESTONE6_VALIDATION.md`.

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

Kadence personality is Project-owned and inference-engine-independent. Accepted character: cool, analytical, precise, competent first, concise in speech, naturally British, with sharp wit/playful sarcasm used naturally rather than constantly. No new robot expression or LED system was added.

### M2 - Control Surface foundation: USER ACCEPTED / CLOSED

Accepted Windows EYE-themed Control Surface provides backend start/stop, robot/server state, ASR/persona/model/transport status, preflight port checks, UTF-8 live logs, packaged EXE launch, project/Conda discovery and narrow stale-Kadence cleanup. It delegates actual voice transport startup to the frozen Alpha 1 path.

Evidence gap retained honestly: the accepting M2 chat did not capture a separate final packaged STOP SERVER-cycle log.

### M3 - Provider benchmark: PASS / CLOSED / HISTORICAL

M3 compared Gemini 3.5 Flash-Lite and GPT-5.6 Luna while keeping identity, ASR, endpointing, TTS and transport constant.

Historical result:

- Gemini won raw provider latency.
- Luna won broader blind answer quality and physical conversational flow.
- Luna became the Alpha 2 default.
- No transport invariant changed to favour either provider.

Historical M3 caveats were corrected before acceptance: an ambient profile override compromised an early blind harness, initial log retention was insufficient, and one cold boot briefly had weaker wakeword pickup before recovering without retuning.

**Post-M5 policy supersedes the old fallback clause:** Gemini is no longer an active fallback and the M3 benchmark harness is retired. The validation records remain authoritative historical evidence.

### M4 - Non-persistent session continuity: PASS / CLOSED

Kadence owns short live-session continuity at backend-process scope rather than inside an inference provider, robot firmware or Xiaozhi durable Memory.

Architecture/limits:

- Project-owned `KadenceSessionHistory` at `WebSocketServer` process scope;
- keyed by stable `device-id`;
- fresh handlers hydrate generic `user`/`assistant` history;
- completed top-level turns commit back to the process store;
- maximum 8 completed exchanges;
- 12,000-character secondary ceiling;
- prune oldest complete exchange first;
- no TTL, summarisation, token counting, vector DB, durable storage, personal profile or SD-card memory.

Physical acceptance proved cross-wake references, three-plus connected turns, clean topic switching, stable persona, reconnect hydration, the 8-exchange cap, backend-restart wipe and normal wake/listen/endpoint/ASR/think/speak/idle behaviour.

M4 history note: the first physical boot failed closed on a brittle patch guard; the guard was narrowed without changing architecture and the subsequent run passed fully.

M4 audio note: one severe crackle occurred on the first post-reconnect Saturn/Titan answer. Server-side TTS reported success and it did not recur. Treat as non-blocking unless reproducible.

### M5 - Safe tool boundary: PASS / CLOSED

Kadence has a physically validated Project-owned allow-list/schema execution gate.

Authority line:

`inference engine proposes call -> Kadence allow-list/schema gate -> Project-owned handler -> structured result -> inference engine final wording`

Not allowed:

`inference engine -> generic Xiaozhi plugin/MCP/IoT registry -> arbitrary executor`

Core tracked implementation retained after simplification:

- `kadence_tools.py`;
- `kadence_tool_runtime.py`;
- `apply_kadence_tools_windows.ps1`;
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

Physical Luna acceptance proved ordinary no-tool conversation, M4 follow-up continuity, allow-listed execution, containment of invented delete/shell requests, tool-turn survival across reconnect, restart wipe, persona stability and frozen transport behaviour.

Gemini was also physically tested solely to prove provider abstraction. An initial Gemini 3 `thought_signature` incompatibility was repaired provider-locally and a final genuine Gemini probe passed. That work completed its architectural purpose and has now been retired from the active runtime path.

Canonical validation record: `MILESTONE5_VALIDATION.md`.

### M6 - First read-only utilities: PASS / CLOSED

Accepted active utility allow-list:

- `kadence_datetime`;
- `kadence_weather`;
- `kadence_web_lookup`.

M6 authority remains the closed M5 boundary. There is no generic HTTP, shell, filesystem, process, MCP, IoT or smart-home executor exposed to Luna.

Weather display architecture:

- trusted handler derives only `clear | cloud | rain | snow`;
- private `_kadence_ui` hint is stripped before factual result reinjection;
- backend emits versioned `type: "kadence"` `weather_icon` event;
- firmware renders a static local pixel-art icon;
- no model-supplied graphic/coordinate/animation path exists;
- normal voice lifecycle restores Idle EYE.

Physically accepted firmware checkpoint: `995a2556f42e030660d6ed651b782987ac4a3d8e`.

Physical acceptance proved named-place datetime, current/future weather, multiple pixel icon classes, factual web lookup, M4 continuity coexistence and normal voice lifecycle.

Physical testing found one real correctness defect: broad `Florida` geocoding selected `Floridablanca, Colombia` through Open-Meteo prefix matching. M6 remained open until this was repaired. Final backend checkpoint `6029c08cdcfbea6861daa4fb7b3cc7290a345569` now inspects a bounded candidate set, prefers exact names and rejects administrative regions/countries as too broad for point weather. Physical retest correctly asked for a city/town and did not fetch a bogus state forecast.

One post-response disconnect/reconnect produced Xiaozhi chat-title `NoneType` and audio close-frame warnings. The server immediately reconnected and hydrated retained exchanges. Record as non-blocking teardown noise; do not reopen transport unless it becomes reproducible or user-visible.

Canonical validation record: `MILESTONE6_VALIDATION.md`.

## Post-M5 provider simplification - ACTIVE POLICY

### Alpha 2 from M6 onward

- **Active LLM: GPT-5.6 Luna only** (`gpt-5.6-luna`, `reasoning_effort: none`).
- Gemini is not a fallback.
- No Gemini regression/acceptance pass is required for M6-M8.
- If Luna fails, Kadence surfaces the failure; it does not silently switch inference providers.
- One OpenAI credential source is used by Luna and OpenAI Realtime ASR in the ignored local runtime.
- Robot firmware remains provider-agnostic; there was no Gemini-specific robot inference path to remove.

### Beta/live target

The accepted future cognition selector is exactly:

- `LOCAL`
- `LUNA`

No `AUTO` mode. No silent LOCAL -> LUNA escalation. No hidden fallback. The selected engine either works or reports failure.

LOCAL does not exist yet and must not be faked into Alpha 2. This remains post-Alpha-2 work.

## Current Alpha 2 operating state

Normal development target is the packaged Control Surface and Alpha 2 Windows backend with:

- canonical Kadence identity;
- GPT-5.6 Luna only;
- OpenAI Realtime ASR;
- Sonia Edge TTS;
- frozen Silero/transport settings;
- bounded volatile M4 session continuity;
- closed M5 safe tool authority boundary;
- closed M6 read-only utilities;
- physically accepted M6 pixel-weather firmware.

Kadence still has no persistent personal memory, vector database, arbitrary OS execution, smart-home writes or model-driven motion. Backend restart intentionally clears M4 continuity.

## CURRENT: Milestone 7 - volatile behaviour overlay

M7 scope is now explicitly locked to **two states only**:

### DEFAULT

- canonical Kadence exactly as accepted;
- no behaviour modifier active.

### CUSTOM

- one operator-supplied free-text behaviour preference from the Control Surface;
- maximum 1,000 characters;
- applied only by an explicit **Apply Custom** action;
- text entry alone has no live effect;
- canonical identity remains the authoritative base;
- custom text may change delivery/style only and cannot override safety, M5 tool rules, M6 utility rules or frozen transport;
- robot disconnect/reconnect retains Custom while the backend process remains alive;
- pressing **DEFAULT** clears Custom immediately;
- backend stop/restart resets to DEFAULT;
- Custom UI field clears on backend start/restart;
- no custom behaviour is written to config, Git, durable memory or a persistent profile.

M7 gate:

1. DEFAULT behaviour is unchanged.
2. An obvious CUSTOM instruction visibly changes delivery.
3. Robot reconnect retains CUSTOM within the same backend process.
4. DEFAULT removes CUSTOM immediately.
5. Backend restart returns to DEFAULT and clears the field.
6. M5/M6 safety/tool boundaries remain unchanged.

Do not add preset mode libraries, persistent behaviour profiles, LOCAL/LUNA selection or any transport work under M7.

## Remaining Alpha 2 roadmap

- M7 - implement/physically validate the locked DEFAULT/CUSTOM volatile behaviour overlay.
- M8 - mixed physical acceptance, exact-state recording and Alpha 2 freeze.

## Parked for post-Alpha-2

Future architecture: **LOCAL / LUNA** with explicit operator selection. Kadence continues to own identity, context/memory policy and tools while the selected inference engine is replaceable.

There is no accepted AUTO router and no automatic fallback policy.

Also parked:

- Tapo/Home Assistant/device writes;
- timers/reminders;
- persistent memory/SD identity;
- continuous conversation/barge-in;
- arbitrary robot expressions/motion.

## Recovery rules

If Alpha 2 becomes unstable:

1. Identify whether regression is current Alpha 2 server work or frozen transport.
2. Do not modify the frozen Alpha 1 branch to fix Alpha 2.
3. Compare against Alpha 1 and accepted Alpha 2 validation records.
4. Preserve branch history; repair forward or revert rather than rewriting validated history.
5. Use `beta/project-kadence` only as the independent older rollback line when needed.
6. Do not resurrect Gemini as a fallback unless the user explicitly reopens that architectural decision.
7. Do not reopen M6 utility/weather firmware unless new physical evidence requires it.
8. If physical evidence suggests a frozen transport invariant truly must change, stop and explicitly reopen that invariant first.

## Resume instruction for a fresh chat

Read live `kadence/2.0-alpha-2`, `ALPHA2_PLAN.md`, `MILESTONE6_VALIDATION.md` and this rolling contingency snapshot. Treat **M0-M6 as closed**. Treat Luna-only operation as current architecture. Treat M7 as exactly DEFAULT plus one 1,000-character maximum volatile CUSTOM behaviour overlay from the Control Surface. Do not create another branch, reopen provider benchmarking, restore Gemini fallback, invent AUTO routing, expose generic MCP/plugin/IoT execution, add preset behaviour modes, persist custom prompts, implement LOCAL/LUNA switching, or retune frozen transport without new physical evidence.
