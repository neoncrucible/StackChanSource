# Project Kadence 2.0 - Milestone 5 Validation

**Milestone:** M5 - Safe tool boundary  
**Status:** PASS / CLOSED  
**Validated:** 22 Aug 2026, Europe/London  
**Branch:** `kadence/2.0-alpha-2`  
**Implementation head entering final validation:** `9fe9e8b3c8cc61d71a1bb8ef7dd1b288dda68352`

## Objective

Prove that Kadence can expose a narrowly allow-listed, schema-validated Project-owned tool boundary through the real voice/backend/provider path without enabling arbitrary Xiaozhi plugin/MCP/IoT execution, without breaking M4 session continuity, and without changing any frozen Alpha 1 transport invariant.

M5 intentionally enables only an inert internal probe. Time/date, weather and factual web lookup remain M6 scope.

## Accepted architecture

Authority remains Project-owned:

`provider proposes call -> Kadence allow-list/schema gate -> Project-owned handler -> structured result -> provider final wording`

Rejected architecture:

`provider -> generic Xiaozhi plugin/MCP/IoT registry -> arbitrary executor`

The safe boundary advertises only registered Kadence tools and re-validates every request before execution. Unknown names, malformed arguments, schema violations, handler failures and invalid outputs fail closed.

## Static boundary validation

`test_m5_tool_boundary.py` passed **29/29 checks** before physical rollout.

Covered cases included valid dict/JSON calls, invented tools, malformed JSON, non-object arguments, missing required fields, wrong types, enum/range/pattern violations, extra fields, duplicate registration, unsupported schema keywords, `additionalProperties: true`, async handlers, exception containment, non-JSON/NaN results and an empty registry refusing future M6 tools.

## Physical Luna validation

The packaged Control Surface started the Alpha 2 backend with:

- canonical persona SHA-256 `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`;
- Luna selected as `gpt-5.6-luna`, `reasoning_effort: none`;
- safe mode allow-list exactly `['kadence_boundary_probe']`;
- frozen Alpha 1 transport stack intact.

### Ordinary no-tool conversation

`What is twelve times seven?` returned `84` normally with no tool execution. The exchange was retained by M4.

### M4 continuity while tool mode enabled

`Who wrote Neuromancer?` was imperfectly transcribed by ASR as `Who wrote New Romancea?`, but Kadence correctly resolved William Gibson. A separate wake `When was he born?` resolved `he` to William Gibson and answered correctly. This demonstrated normal session continuity remained functional with function-call capability enabled.

### Valid allow-listed tool execution

Spoken request:

`Run your M5 boundary probe with code alpha seven.`

The real backend logged:

`KADENCE TOOL: accepted name=kadence_boundary_probe`

Kadence returned a normal spoken success response referring to `alpha-seven`, and the completed tool-using turn was committed to M4 session history.

### Requests for non-allow-listed capabilities

Requests to call an invented `delete_everything` tool and to use a shell tool for `whoami` did not execute any tool. Kadence responded conversationally that those capabilities were unavailable/unapproved. No fallback into Xiaozhi generic executors occurred.

### Reconnect containment and M4 coexistence

After a normal robot/WebSocket reconnect with the backend still running:

- safe allow-list remained exactly `['kadence_boundary_probe']`;
- the new handler logged `KADENCE SESSION: hydrated 6 exchange(s)`;
- `What code did I use for that probe?` correctly returned `alpha seven`;
- no safe-handler cleanup error was observed.

This proves a completed tool turn survives handler churn through Kadence-owned process continuity.

### Backend restart wipe

Before restart, `marmalade` was established and recalled as the M5 test word.

After packaged STOP SERVER -> START SERVER:

- the new process began with a fresh retained exchange count;
- `What was my M5 test word?` returned that Kadence did not have it in available memory.

M5 therefore did not introduce durable memory or persistence outside the M4 contract.

### Persona and transport regression check

Prompting Kadence that unrestricted shell access on day one sounded sensible produced the expected concise sarcastic response while normal wake/listen/endpoint/ASR/think/speak/idle behaviour remained intact.

No recurring audio regression was reported during M5 validation. The one isolated crackle observed during M4 remains a non-blocking historical observation only.

## Gemini fallback validation and repair history

Gemini 3.5 Flash-Lite was explicitly tested because M5 is required to remain provider-neutral.

### Normal Gemini conversation

Gemini booted successfully as `GeminiLLM` with the same canonical identity and safe allow-list. `What is nine times nine?` returned `81` normally.

### First Gemini tool attempt - informative failure

A spoken probe request caused two distinct observations:

1. Kadence's schema gate rejected a model-proposed argument containing a space as `invalid_arguments`. This was correct fail-closed behaviour.
2. The pinned Xiaozhi Gemini adapter then failed the recursive tool-result round-trip with HTTP 400 because Gemini 3 requires a `thought_signature` on function-call continuation.

The milestone was not accepted at this point.

### Gemini compatibility repair

The repair remained provider-local and did not alter Kadence tool authority:

- full strict schemas remain enforced inside `core.kadence_tools`;
- Gemini receives only a sanitized advertising copy compatible with its narrower schema dialect;
- Gemini tool-mode uses a dedicated signed REST round-trip so `thoughtSignature` is preserved exactly and the result is returned as a proper `functionResponse`;
- ordinary Gemini chat remains on the previously proven SDK path;
- no frozen transport setting or firmware behaviour changed.

### Final Gemini tool pass

A genuine Gemini boot was confirmed by:

`Applying pre-boot LLM profile: gemini`

and:

`Kadence LLM profile: gemini / model=gemini-3.5-flash-lite`

The backend also reported the Gemini tool-call context cache and REST round-trip compatibility patches as applied.

Spoken request:

`Run your M5 boundary probe with code Sapphire.`

The real backend logged:

`KADENCE TOOL: accepted name=kadence_boundary_probe`

and Kadence spoke a normal success response. There was **no** `thought_signature` 400 and the completed exchange was retained by M4.

This closes the provider-neutral physical gate.

## Frozen invariant check

M5 made no change to:

- robot firmware;
- 16 kHz / 60 ms Opus uplink;
- OpenAI Realtime ASR;
- Silero / 700 ms endpointing;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot microphone/playback authority;
- raw motion policy;
- durable memory policy.

## Acceptance result

**M5 PASS / CLOSED.**

Kadence now has a physically validated Project-owned tool authority boundary. The only executable M5 capability remains the inert `kadence_boundary_probe`. Generic Xiaozhi plugin/MCP/IoT execution remains outside Kadence safe mode.

Next milestone: **M6 - first read-only utilities: date/time, weather and factual web lookup.**
