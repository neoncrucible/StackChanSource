# Kadence 2.0 Alpha 2 — Milestone 7 Validation

Status: **PASS / CLOSED / PHYSICALLY ACCEPTED**

Date accepted: **23 Aug 2026**  
Branch: `kadence/2.0-alpha-2`

Physically accepted M7 implementation checkpoint:

`db4db895c4bf4ae6f39e360675a52ed7d185346f`

CI at that checkpoint:

- `kadence-alpha/backend-tests`: **success**
- `kadence-alpha/firmware-build`: **success**

Canonical persona SHA-256 remains:

`7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`

Pinned Xiaozhi upstream remains:

`e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

## Scope accepted

M7 implements exactly two operator behaviour states:

- **DEFAULT** — canonical Kadence unchanged.
- **CUSTOM** — one volatile free-text behaviour overlay supplied from the Windows Control Surface.

The overlay is deliberately narrow:

- maximum 1,000 characters;
- typing alone has no live effect;
- an explicit **Apply Custom** action is required;
- canonical Kadence remains the authoritative base prompt;
- custom text may influence tone, verbosity, formatting, conversational stance or delivery style only;
- custom text cannot grant capabilities or override safety, M5 tool schemas/authority, M6 utility authority, memory policy, transport invariants, provider selection or canonical identity;
- no custom text is written to config, Git, durable memory or a persistent profile;
- backend restart always returns to DEFAULT.

## Runtime/control architecture

Project-owned `kadence_behavior.py` owns one process-lifetime behaviour string in RAM.

The Windows Control Surface talks only to the loopback endpoint:

`http://127.0.0.1:8766/v1/behavior`

This control path is separate from the robot WebSocket transport. Robot disconnect/reconnect therefore does not itself clear a CUSTOM overlay while the backend process remains alive.

At the beginning of a top-level user turn, M7 composes the current behaviour overlay onto the already-established canonical prompt. The canonical prompt itself is not replaced or persisted in modified form.

## Control Surface acceptance

The accepted Control Surface revision is V4.5.

User-visible M7 surface:

- `DEFAULT` action;
- free-text `CUSTOM` editor;
- explicit `APPLY CUSTOM` action;
- 1,000-character editor bound;
- behaviour state indicator.

V4.5 also repaired two operator-UI defects found during physical validation:

- the CUSTOM editor remains writable while the backend is offline so a prompt can be prepared before startup;
- DEFAULT / APPLY CUSTOM remain readable in the same cyan/dark-panel visual language as the existing server controls.

The EYE graphic was also reduced to 90% and recentered after the earlier left-rail resize had left its right edge clipped. This was a Control Surface geometry repair only; it did not alter robot expressions or firmware.

## Implementation defects found and repaired before acceptance

Physical startup testing found several fail-closed/idempotence defects. They were repaired without reopening the frozen transport:

1. The first M7 shutdown guard depended on a translated surrounding comment. It was replaced with a formatting-tolerant guard anchored to the unique executable `await gc_manager.stop()` site.
2. An M7 import insertion omitted a trailing newline and produced a fused Python import in `connection.py`. The applier now repairs that legacy malformed state and owns the newline explicitly.
3. After M7 enhanced the root-turn block, the older M5 exact-text patcher no longer recognised the valid shape and failed closed. Startup now uses an M5 compatibility wrapper that verifies the real M5 authority markers and safely skips the obsolete textual patcher when an already-valid M7-enhanced runtime is present.
4. Dedicated regression coverage was added for the M7/M5 compatibility state and duplicate-root-capture fail-closed behaviour.

These repairs changed patch/application idempotence only. They did not change M5 authority, M6 utilities, ASR, endpointing, TTS or robot transport.

## Physical acceptance evidence

Physical testing proved:

- backend startup with M5/M6 authority preserved and M7 loopback control ready in DEFAULT;
- normal canonical behaviour before CUSTOM was applied;
- explicit CUSTOM application generated both Control Surface and backend state-change evidence;
- an obvious custom instruction changed subsequent answer delivery (`Diagnostic:` one-sentence behaviour);
- a second custom behaviour was visibly expressed on a personality-friendly prompt while trivial arithmetic correctly remained terse/utility-first;
- pressing DEFAULT immediately restored canonical behaviour;
- robot disconnect/reconnect retained CUSTOM while the same backend process remained alive — user-confirmed physical PASS;
- backend stop/restart cleared CUSTOM and returned to DEFAULT — user-confirmed physical PASS;
- M4 continuity and M5/M6 authority remained intact during the M7 session.

The operator correctly observed that a trivial question such as `5 × 5` may not visibly express a stylistic overlay because canonical Kadence remains utility-first. A changed question then made the active custom behaviour obvious. This is accepted behaviour, not an override failure.

## Non-blocking observation retained

During an earlier DEFAULT-mode test, a relatively long neutron-star answer completed through TTS and the robot/client subsequently disconnected. No CUSTOM overlay had been applied at that point. The backend remained alive; after backend restart the robot had not yet reconnected, which explained the apparent wake-word failure.

This incident is not evidence that M7 breaks wake-word detection, and it does not justify reopening frozen transport. Treat the long-response disconnect as a separate non-blocking observation unless it becomes reproducible under a deliberate transport-focused test.

## Acceptance result

**Milestone 7 is CLOSED.**

Accepted behaviour contract:

`DEFAULT canonical Kadence | CUSTOM volatile behaviour overlay`

No preset library, persistent profile, LOCAL/LUNA selector, AUTO routing, new expression system or transport retuning was added.

Next milestone: **M8 — mixed physical acceptance, exact-state recording and Alpha 2 freeze.**
