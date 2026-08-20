# Kadence 2.0 Alpha 2 — Milestone 2 Validation

Status: **USER ACCEPTED / FOUNDATION VALIDATED**

Date: **20 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Purpose

Milestone 2 establishes a usable Windows Kadence Control Surface around the frozen Alpha 1 transport stack. Its required foundation is server boot, server monitoring, health/state display, live log visibility and an operator-facing Kadence EYE identity. Provider switching and session personality controls remain deferred.

## Accepted implementation

The accepted Control Surface provides:

- EYE-themed Windows operator UI;
- explicit `START SERVER` / `STOP SERVER` controls;
- server, robot, ASR, persona, model and transport status surfaces;
- live server log and last-heard area;
- preflight checks for UDP 45872 and TCP 8000/8003;
- UTF-8 backend log capture to avoid Windows CP1252/Loguru failures;
- packaged `Kadence Control Surface.exe` launcher with a Kadence EYE icon;
- project discovery from the packaged launcher;
- Alpha 2 Conda discovery before delegating to the frozen Alpha 1 launcher;
- a narrow stale-Kadence cleanup helper for the dedicated `kadence2-xiaozhi` Python backend signature.

## Physical acceptance run

The packaged Control Surface was launched successfully from Windows and started the Alpha 2 backend from the UI.

Observed startup markers included:

- `=== Kadence 2.0 Alpha 2 ===`;
- canonical persona SHA-256 `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`;
- `Kadence Conda discovery: C:\Users\denma\miniconda3`;
- handoff to the frozen Alpha 1 transport launcher;
- pinned Xiaozhi upstream `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5` verified;
- `OpenaiRealtimeASR` selected;
- server endpoint silence hold remained `700 ms`;
- discovery bridge remained UDP 45872 to Xiaozhi WebSocket port 8000;
- Xiaozhi WebSocket and HTTP services started normally;
- UTF-8 Chinese Loguru output displayed without the previous CP1252 encoding failure.

The packaged EXE initially exposed a clean-process PATH issue where `conda` was not inherited. Alpha 2 was corrected to discover the local Miniconda/Anaconda installation before handing off to the untouched frozen launcher. The repeated packaged run then booted successfully.

## Port-conflict behaviour

During development, the Control Surface correctly blocked startup when stale Xiaozhi `python.exe app.py` PID 16608 owned TCP 8000 and 8003, and reported that exact owner instead of starting a second backend blindly.

A narrow cleanup helper is now present for the dedicated Kadence backend signature. It is intentionally constrained so unrelated processes are not killed merely for occupying one required port.

## Transport boundary

Milestone 2 did **not** retune or replace the frozen Alpha 1 transport. The Control Surface and Alpha 2 wrapper sit outside the validated transport path and continue to delegate actual server startup to the inherited Alpha 1 launcher.

No firmware, endpoint hold, Realtime ASR selection, final Opus flush, AFE fallback, microphone authority or playback lifecycle setting was changed for Milestone 2.

## Accepted deferrals / non-blockers

The following are explicitly deferred and do not block Milestone 2 acceptance:

- further UI spacing/alignment/polish;
- provider/model toggle;
- session behaviour/personality modifiers;
- benchmark controls/graphs;
- richer transcript and latency visualisation;
- general Python 3.10 migration warning cleanup.

The final packaged boot and monitor path is physically accepted by the user. The STOP SERVER path is implemented, but this chat does not contain a separately captured final packaged stop-cycle log; that is recorded as an evidence gap rather than falsely claimed as a witnessed result.

## Decision

**Milestone 2 foundation is accepted and signed off.**

UI polish may continue later without reopening the milestone or touching the frozen Alpha 1 transport.

Next planned milestone: **Milestone 3 — Gemini vs OpenAI benchmark / default LLM selection.**
