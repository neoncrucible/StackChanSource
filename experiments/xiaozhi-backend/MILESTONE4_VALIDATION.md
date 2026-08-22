# Kadence 2.0 Alpha 2 — Milestone 4 Validation

Status: **PASS / CLOSED — non-persistent session continuity physically validated**

Date: **22 Aug 2026**

Branch: `kadence/2.0-alpha-2`

Implementation commits:

- `587052fc88e08c1d5e7cc7d20c541f640caea3cf` — initial M4 session continuity implementation
- `063bb7a497ee1d179c1a0783a64cf287810edfca` — narrowed runtime handler hook after first fail-closed physical startup exposed an overly brittle patch guard

## Decision

Milestone 4 is accepted and closed.

Kadence now owns short, volatile conversational history at backend-process scope rather than inside Luna, Gemini, the robot, or Xiaozhi's durable Memory subsystem. The session store is provider-neutral and keyed by stable robot `device-id`.

Accepted limits:

- maximum **8 completed user/assistant exchanges**;
- secondary **12,000-character** ceiling;
- pruning removes the oldest complete exchange;
- no token counting;
- no summarisation;
- no inactivity TTL;
- no durable persistence;
- no personal profile, vector database or SD-card memory.

Backend restart destroys the session store by construction.

## Implementation boundary

Project-owned implementation:

- `experiments/xiaozhi-backend/kadence_session.py`
- guarded runtime wiring in `experiments/xiaozhi-backend/patch_runtime_windows.ps1`

The runtime patch installs the Project-owned helper into the ignored pinned Xiaozhi runtime, owns one `KadenceSessionHistory` at `WebSocketServer` process scope, attaches it to each fresh `ConnectionHandler`, hydrates generic `user`/`assistant` messages into a fresh `Dialogue`, and commits only completed top-level spoken exchanges.

No provider adapter was changed. Luna/OpenAI and Gemini continue to consume the same generic Xiaozhi `Dialogue` request path.

No Alpha 1 transport invariant, robot firmware, ASR, VAD threshold, endpoint hold, Opus behaviour, TTS provider or playback lifecycle contract was changed for M4.

## First physical startup — fail-closed guard event

The first M4 physical startup stopped before backend launch with:

`Kadence M4 handler injection guard failed; refusing to modify runtime.`

This was traced to an overly brittle PowerShell patch anchor that matched the full upstream `ConnectionHandler(...)` constructor call including a non-ASCII inline comment. The architecture itself was not implicated.

The hook was narrowed to an ASCII-only attachment immediately before `handler.handle_connection(websocket)`, preserving the same process-owned session architecture. The runtime patch remained guarded and fail-closed.

The corrected startup then installed all M4 runtime hooks successfully.

## Physical acceptance evidence

### A. Reference resolution across separate wake turns — PASS

Physical sequence:

1. `Who wrote Dune?`
2. Kadence answered that Dune was written by Frank Herbert.
3. Separate wake: `When was he born?`
4. Kadence correctly resolved `he` to Frank Herbert and answered 8 October 1920.

The session log advanced from retained exchange count 1 to 2.

### B. Multi-step continuity — PASS

Further separate wake turns remained coherent:

- `What nationality was he?` → Frank Herbert was American.
- `What other famous books did he write?` → response remained correctly about Frank Herbert.

The retained session count advanced through 3 and 4.

### C. Unrelated topic transition — PASS

The conversation switched from Frank Herbert/Dune to:

- `What is the capital of Japan?` → Tokyo.
- `What is its population roughly?` → correctly interpreted `its` as Tokyo.

Old Dune context did not contaminate the new topic.

### D. Canonical persona stability — PASS

Prompt:

`I reckon buying six more unfinished electronics projects is sensible financial planning.`

Kadence responded in the accepted concise/dry personality, including the line that otherwise it was `a small museum of future guilt`.

Canonical persona SHA observed at boot remained:

`7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`

### E. Reconnect continuity — PASS

Before reconnect, Kadence was explicitly told that the next questions concerned Saturn and answered the first Saturn question. The retained exchange count reached the configured cap of 8.

A new WebSocket/ConnectionHandler then connected while the backend process remained alive. The new handler logged:

`KADENCE SESSION: hydrated 8 exchange(s)`

After the reconnect, the separate wake question:

`Which is the biggest one?`

correctly resolved the prior subject and answered that Titan is Saturn's largest moon.

This is direct physical proof that continuity is backend-session-owned and survives per-socket handler churn.

### F. Bounded retention — PASS

The retained exchange count reached 8 and remained at 8 on later completed turns, demonstrating bounded pruning rather than unbounded growth.

### G. Backend restart wipe — PASS

Before restart:

- user set the session test word to `mongoose`;
- later `What is my test word?` correctly returned `mongoose`.

The Control Surface then stopped and restarted the backend.

After restart:

- the next `What is my test word?` response was `I don’t have a test word stored in my memory`;
- the new process logged `KADENCE SESSION: retained exchange count=1` after that first new turn rather than hydrating the prior session.

This demonstrates that M4 continuity is non-persistent and is destroyed by backend restart.

### H. Transport regression — PASS

Normal physical wake/listen/endpoint/ASR/think/speak/idle operation remained functional throughout the acceptance run.

Observed endpoint requests remained around the frozen 700 ms sustained-silence behaviour, and OpenAI Realtime ASR completed normally after commits. A final unrelated post-restart question about Europe's tallest mountain completed normally.

## Audio anomaly observation

One instance of severe audible crackle was reported by the physical operator during the first post-reconnect Saturn answer (`Which is the biggest one?`).

The server log for that answer shows both TTS segments generated successfully with zero retries and no corresponding M4/session error. The anomaly occurred shortly after a WebSocket reconnect and old-connection resource release, so a transient playback/network/robot-side handoff remains plausible, but the log does not establish a cause.

Because the crackle occurred once, did not repeat during the rest of the run, and all transport/session acceptance gates passed, it is recorded as a **non-blocking observation**. Do not retune frozen transport or playback behaviour for this event alone. Reopen investigation only if the crackle becomes reproducible.

## Milestone 4 conclusion

M4 acceptance gates are satisfied:

- reference resolution across separate wake turns: **PASS**;
- three-plus connected wake turns: **PASS**;
- unrelated topic separation: **PASS**;
- reconnect/handler churn continuity: **PASS**;
- bounded session retention: **PASS**;
- backend restart wipe: **PASS**;
- canonical persona stability: **PASS**;
- normal transport regression: **PASS**;
- frozen Alpha 1 transport invariants unchanged: **PASS**.

Milestone 4 is therefore **CLOSED**.

Next milestone: **Milestone 5 — safe, schema-validated, allow-listed tool boundary with fail-closed handling for malformed, unknown or invented calls.**
