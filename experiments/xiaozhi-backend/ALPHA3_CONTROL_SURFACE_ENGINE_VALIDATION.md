# Project Kadence 2.0 — Alpha 3 Control Surface Engine Validation

Physically validated on Windows: 24 Aug 2026

## Scope

This checkpoint closes the Alpha 3 Control Surface engine-selection slice.

It validates explicit LOCAL / LUNA selection, start, chat, stop, and fail-closed behaviour. It does not validate robot integration, firmware changes, Home Assistant, timers, persistent memory, AUTO routing, motion, expressions, LED work, or future personality tuning.

## Accepted code checkpoints

Branch: `kadence/2.0-alpha-3`

Frozen Alpha 2 closure remains unchanged:

`c74d8949f33c6dea1d7df2bea248cad9e82d5dd1`

Physically accepted LOCAL standalone validation checkpoint:

`a5af604eca1c356bcfe1094392c85f71e604543e`

Physically accepted LOCAL Control Surface validation checkpoint:

`9858b9972318406a70c16debb3f88b40251baf75`

Current Control Surface engine implementation under this gate includes:

- Windows PowerShell Generic.List compatibility guards;
- script-scoped WinForms chat event handlers;
- quiet Enter-to-send via WinForms `AcceptButton`;
- explicit UTF-8 decode for LUNA chat responses.

## LOCAL positive-path evidence

Physically proven through the real Control Surface:

- LOCAL is visibly selected before start;
- START launches only the project-owned LOCAL runtime;
- `qwen3.5:4b` loads 100% on the target GPU with context 8192;
- engine selectors lock while running;
- CHAT is disabled before readiness and enabled only after LOCAL is ready;
- LOCAL Control Surface text chat completes successfully;
- canonical Kadence persona is present;
- short multi-turn context works;
- STOP shuts down the project-owned LOCAL runtime;
- TCP 11434 is released;
- no LUNA fallback occurs.

## LUNA positive-path evidence

Physically proven through the real Control Surface:

- LUNA is visibly selected before start;
- selecting LUNA while idle does not start either engine;
- START launches only the frozen Alpha 2 backend path;
- canonical Kadence identity is loaded;
- accepted LUNA profile resolves to `gpt-5.6-luna` with `reasoning=none`;
- pinned Xiaozhi transport remains unchanged;
- CHAT is enabled only after backend readiness;
- LUNA Control Surface text chat completes successfully;
- short multi-turn context works;
- Enter-to-send is silent after the WinForms `AcceptButton` fix;
- UTF-8 punctuation is rendered correctly, including `Boss—it’s fixed now.`;
- STOP reports `Backend stopped.`;
- no LOCAL fallback occurs.

## LOCAL fail-closed evidence

A deliberate foreign TCP listener was created on port 11434.

With LOCAL selected, START reported:

- `LOCAL START BLOCKED: TCP 11434 is already in use.`
- the foreign PowerShell PID was identified;
- `Kadence will not hijack an existing Ollama service.`

A separate check confirmed no listener appeared on TCP 8000.

Result: failed LOCAL startup did not launch LUNA.

## LUNA fail-closed evidence

A deliberate foreign TCP listener was created on port 8000.

With LUNA selected, START reported:

- `START BLOCKED: required local port(s) already in use.`
- the foreign PowerShell PID was identified on TCP 8000.

A separate check confirmed no listener appeared on TCP 11434.

Result: failed LUNA startup did not launch LOCAL.

## Result

**PHYSICALLY ACCEPTED — Alpha 3 Control Surface engine-selection slice CLOSED.**

Accepted behaviour:

- explicit LOCAL / LUNA only;
- no AUTO routing;
- no silent fallback;
- selected engine is obvious before start;
- START launches only the selected engine;
- STOP cleans the selected engine;
- LOCAL chat works;
- LUNA chat works;
- short multi-turn context works on both paths;
- quiet Enter-to-send works;
- LUNA UTF-8 response rendering works;
- LOCAL failure surfaces with no LUNA fallback;
- LUNA failure surfaces with no LOCAL fallback;
- frozen Alpha 2 transport and firmware invariants remain untouched.

## Deferred / next slice

The next Alpha 3 slice may begin LOCAL robot integration while preserving the frozen transport invariants.

Cosmetic Control Surface cleanup remains non-blocking and includes stale labels such as the LOCAL pre-boot footer while LUNA is selected and legacy wording such as `START SERVER` in one conflict message.
