# Project Kadence 2.0 — Alpha 3 LOCAL Bring-Up

Prepared: 24 Aug 2026

## Provenance

Alpha 3 branch: `kadence/2.0-alpha-3`

Created directly from frozen Alpha 2 closure commit:

`c74d8949f33c6dea1d7df2bea248cad9e82d5dd1`

Creation-time comparison was identical: 0 commits ahead, 0 behind.

Frozen Alpha 2 remains historical validated state and must not be modified.

## First Alpha 3 slice

The first slice is deliberately server-only and robot-free.

Objective:

1. Start one Project-owned LOCAL inference runtime on Windows.
2. Feed it the existing canonical Kadence identity at request time.
3. Prove factual and personality responses.
4. Stop cleanly.
5. Restart cleanly.
6. Prove TCP 11434 is not leaked.
7. Measure actual local latency before selecting the long-term model.

No Xiaozhi voice server, robot firmware, robot transport, Home Assistant, timers, persistent memory, AUTO routing, M7 behaviour controls or JSON profile upload is part of this slice.

## Runtime choice

Initial runtime: Ollama on Windows.

Why:

- native Windows/NVIDIA path;
- stable local HTTP API;
- straightforward process lifecycle;
- current pinned Xiaozhi upstream already contains an Ollama LLM provider for the later robot-integration stage;
- model remains replaceable.

The Project starts its own `ollama serve` process on `127.0.0.1:11434` and refuses to hijack a listener it does not own.

Runtime state and model files are stored below ignored `.runtime/local/ollama/`.

Cloud features are disabled for the Project-owned process.

## Initial model candidate

First physical candidate: `qwen3.5:4b`.

This is provisional, not a final architecture lock.

The first test captures actual wall time, Ollama total/load time and generation throughput. If latency, instruction following or Kadence personality consistency are weak, benchmark the next sensible candidate rather than tuning around a bad model choice.

## Identity contract

LOCAL reads:

`persona/KADENCE_CANONICAL.md`

on every prompt and refuses inference unless its SHA-256 is exactly:

`7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`

The persona is supplied as a system message. It is not baked into model weights or an Ollama Modelfile.

## Scripts

- `start_local_windows.ps1` — starts the Project-owned Ollama process, verifies port ownership, optionally pulls the candidate, and preloads it.
- `invoke_local_windows.ps1` — verifies runtime ownership and canonical persona hash, then sends a LOCAL prompt.
- `stop_local_windows.ps1` — unloads the model, validates process ownership, kills only the owned process tree, and verifies TCP 11434 is released.
- `test_local_windows.ps1` — complete first physical test sequence.

## Physical gate

Run from `experiments/xiaozhi-backend`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\test_local_windows.ps1
```

First execution may download the candidate model.

Acceptance evidence must include the three responses plus the metrics table. Do not mark the LOCAL slice physically validated until that output has been reviewed.

## Deferred until LOCAL standalone passes

Only after the standalone gate passes:

- select/confirm the LOCAL model;
- add explicit LOCAL/LUNA selection to the existing M6 + EYE Control Surface;
- make Start Server launch only the selected cognition path;
- make Stop Server clean up only the active path;
- prove no fallback in either direction.

Robot integration remains a later gate.
