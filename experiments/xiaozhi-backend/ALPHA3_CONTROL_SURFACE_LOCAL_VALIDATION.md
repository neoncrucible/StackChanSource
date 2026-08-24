# Project Kadence 2.0 — Alpha 3 Control Surface LOCAL Validation

Physically validated on Windows: 24 Aug 2026

## Scope

This checkpoint validates the Alpha 3 Control Surface LOCAL path only.

It does not validate the LUNA selector path, robot integration, firmware, transport changes, Home Assistant, timers, persistent memory, AUTO routing, or retired M7 behaviour controls.

## Code under test

Branch: `kadence/2.0-alpha-3`

Physical LOCAL standalone baseline:

`a5af604eca1c356bcfe1094392c85f71e604543e`

Control Surface LOCAL/chat runtime checkpoint:

`e93afbdc74442dbc796dfbe195543b95e655d168`

Frozen Alpha 2 remains unchanged.

## Physical operator evidence

The operator launched `start_control_surface.ps1` and observed the pre-start Alpha 3 surface with:

- `ALPHA 3` visible;
- explicit `LOCAL` / `LUNA` engine controls;
- `LOCAL` selected before startup;
- `qwen3.5:4b` shown as the selected LOCAL model;
- `START` enabled;
- `STOP` and `CHAT` disabled;
- robot / ASR / transport marked deferred for the LOCAL server-only slice;
- accepted EYE geometry preserved;
- no AUTO selector;
- no retired M7 DEFAULT/CUSTOM controls.

The operator then clicked START. The Control Surface reported:

- `LOCAL READY`;
- `qwen3.5:4b` loaded at 3.3 GB;
- 100% GPU placement;
- context 8192;
- START disabled;
- STOP enabled;
- CHAT enabled;
- LOCAL/LUNA selection locked while running;
- log text explicitly stating that no LUNA fallback was configured.

## Control Surface text chat

The operator opened CHAT and, after two Windows PowerShell 5.1 compatibility bugs were found and fixed during physical testing, successfully completed a LOCAL text session through the real Control Surface.

First successful prompt:

`Kadence, I’ve just spent twenty minutes debugging something that turned out to be a loose USB cable. What do you reckon?`

Observed response:

`Twenty minutes for a loose cable. Typical. It's the digital equivalent of waiting for your bus while it's already stopped at the curb.`

The response continued with a practical follow-up, confirming that the canonical Kadence persona was active through the Control Surface bridge.

A second prompt in the same chat session asked:

`What did I just waste twenty minutes debugging?`

Kadence correctly answered that it was the loose USB cable and expanded on the earlier context. This physically validates short multi-turn Control Surface chat continuity.

The Control Surface chat context remains deliberately separate from the robot voice-session context in this Alpha 3 slice.

## Windows PowerShell compatibility fixes proven during the gate

Physical testing exposed and resolved two WinForms / Windows PowerShell 5.1 issues:

1. forcing `Generic.List[object]` through `@(...)` caused `Argument types do not match`;
2. `.GetNewClosure()` isolated the CHAT event handler from the real Control Surface script state and left the Enter handler unable to retrieve `$SendAction`.

The accepted checkpoint uses direct enumeration / `.ToArray()` plus script-scoped chat event handlers, with static regression guards for both failure modes.

## Stop / cleanup evidence

The operator closed the chat and clicked STOP. The live Control Surface log reported:

- `Stopping Project-owned LOCAL runtime...`
- `LOCAL stopped; TCP 11434 released.`

This follows the already physically accepted ownership-aware LOCAL stop path, which explicitly verifies listener release.

## Result

**PHYSICALLY ACCEPTED for the Alpha 3 Control Surface LOCAL slice.**

Accepted behaviour:

- explicit LOCAL selection visible before start;
- START launches only LOCAL;
- LOCAL uses the Project-owned Ollama runtime;
- `qwen3.5:4b` runs 100% on the target GPU;
- engine selection locks while running;
- CHAT is enabled only after LOCAL is ready;
- Control Surface LOCAL chat works;
- canonical persona is present;
- short multi-turn chat continuity works;
- no LUNA fallback occurs;
- STOP cleans the LOCAL path and releases TCP 11434;
- existing M6 + EYE visual base remains intact;
- no AUTO mode or retired M7 behaviour controls are present;
- no robot, firmware, or transport implementation was reopened.

## Remaining Alpha 3 Control Surface gate

Validate the explicit LUNA path next:

- select LUNA while idle;
- verify the selected engine is obvious before start;
- START launches only the frozen Alpha 2 LUNA path;
- CHAT routes only to LUNA;
- existing Alpha 2 Luna behaviour remains functional;
- STOP cleans only the LUNA backend;
- LUNA failure must surface with no LOCAL fallback.

After the LUNA path is physically accepted, the Control Surface selector slice can be closed and LOCAL robot integration can begin.