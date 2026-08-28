# Project Kadence 2.0 - Alpha 3

## Rolling Contingency Snapshot

**Status:** ACTIVE ALPHA 3 / M1 + M2 + PERSONA V2 ACCEPTED / M3 NEXT  
**Snapshot:** 28 Aug 2026, Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Active branch:** `kadence/2.0-alpha-3`  
**Active Windows repo:** `C:\AI Project\Project-Kadence-2.0`

## Purpose

This is the Alpha 3 successor to the frozen Alpha 2 rolling contingency.

The Alpha 2 PDF remains a historical recovery artifact and must not be overwritten to describe Alpha 3. This document captures the current Alpha 3 state, accepted checkpoints, local disk layout, next milestone, rollback rules and deferred work.

Use this PDF together with:

- `experiments/xiaozhi-backend/ALPHA3_FRESH_CHAT_HANDOVER_2026-08-28.md`
- `experiments/xiaozhi-backend/ALPHA3_MILESTONES.md`
- the live `kadence/2.0-alpha-3` branch

If an older chat conflicts with this snapshot and the live branch, prefer this snapshot and live source.

## Current code and documentation anchors

Latest code/persona anchor physically used before this documentation refresh:

`1b1518ff7ea0bdc016e63e19c65906b015bf9692`

Documentation refresh anchors:

- milestone roadmap refresh: `3e642e7a16091dac89fef63219b95e9154a1ce4f`
- clean-slate handover: `f5ae4f8f16bf3e583c35fc77006608dbdbd71965`

At the operator's pre-refresh inspection, local HEAD and remote Alpha 3 HEAD both resolved to `1b1518ff...`. The branch was therefore in sync before these documentation-only updates.

## Preserved local working state

Do not reset or delete the following simply to make `git status` clean.

Modified local files:

- `firmware/fetch_repos.py`
- `firmware/tools/apply_m6_pixel_weather_display.py`

Untracked/generated local paths:

- `experiments/xiaozhi-backend/.tools/`
- `experiments/xiaozhi-backend/__pycache__/`
- `experiments/xiaozhi-backend/control_surface/KadenceControl-run-*.ps1`
- `experiments/xiaozhi-backend/tmp/`

These were present while the local commit still exactly matched the remote branch.

## Active Windows layout

Primary active root:

`C:\AI Project\Project-Kadence-2.0`

Relevant locations:

- `C:\AI Project\Archive\...` - historical only
- `C:\AI Project\Kadence-2.0-flash` - separate flash workspace
- `C:\AI Project\Kadence-Flash\M6-Pixel-Weather-995a255` - accepted M6 flash checkpoint
- `Project-Kadence-2.0\docs\checkpoints` - checkpoint documents
- `Project-Kadence-2.0\experiments\xiaozhi-backend` - active Windows backend work
- `...\xiaozhi-backend\.runtime\local\ollama\models` - LOCAL model store
- `...\xiaozhi-backend\.runtime\xiaozhi-esp32-server` - pinned/materialized Xiaozhi runtime
- `...\xiaozhi-backend\control_surface` - Control Surface patch chain
- `...\xiaozhi-backend\persona` - canonical identity
- `Project-Kadence-2.0\firmware` - firmware source

Do not resume from a similarly named historical repo under `Archive`.

## Frozen Alpha 2 recovery anchors

Frozen branch:

`kadence/2.0-alpha-2`

Alpha 2 closure/documentation head:

`c74d8949f33c6dea1d7df2bea248cad9e82d5dd1`

Final physically accepted Alpha 2 runtime/source anchor:

`348e7c0fc05a027ba9affc7677534e488bd338c9`

Additional anchors:

- Alpha 2 M6 backend validation: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- accepted M6 pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`
- frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- physically validated Alpha 1 firmware: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- independent rollback: `beta/project-kadence`
- pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

## Frozen transport invariants

Do not change these while implementing M3 unless new physical evidence proves a deliberate reopen is necessary:

- Xiaozhi v1 bidirectional WebSocket transport
- 16 kHz / 60 ms Opus robot uplink
- OpenAI Realtime ASR on the accepted robot/LUNA path
- Windows Silero preferred endpointing
- 700 ms sustained-silence hold
- ESP32 AFE fallback
- 180 ms final Opus flush
- 10 s hard capture cap
- robot-owned microphone stop, final flush and playback lifecycle
- versioned Project-owned control messages
- no model-selected arbitrary robot movement

Keep the accepted Sonia Edge TTS path, M6 read-only tools, safe tool boundary, EYE geometry and weather icon contract intact.

Retired M7 DEFAULT/CUSTOM behaviour controls must not return.

No AUTO cognition routing. No silent provider fallback.

## Alpha 3 milestone state

### A3-M1 - LOCAL standalone inference

**CLOSED / PHYSICALLY ACCEPTED**

Accepted:

- Project-owned Ollama runtime
- `qwen3.5:4b`
- about 3.3 GB model
- 8192 context
- 100 percent GPU placement on RTX 3060 Laptop 6 GB
- factual response
- Kadence personality response
- clean stop
- restart
- no TCP 11434/process leak

Accepted validation checkpoint:

`a5af604eca1c356bcfe1094392c85f71e604543e`

### A3-M2 - Explicit LOCAL/LUNA Control Surface

**CLOSED / PHYSICALLY ACCEPTED**

Accepted:

- explicit LOCAL / LUNA selection
- no AUTO
- selected engine obvious before start
- START launches only selected path
- STOP cleans selected path
- LOCAL text chat
- LUNA text chat
- short multi-turn context on both
- silent Enter-to-send
- explicit UTF-8 response decode for LUNA
- successful punctuation rendering
- fail-closed LOCAL conflict test on TCP 11434
- fail-closed LUNA conflict test on TCP 8000
- no cross-provider fallback
- frozen Alpha 2 LUNA backend still starts
- no committed firmware delta required

Accepted closure checkpoint:

`06b3b61669fa3fc3a6041e73613dccffdbdbd63b`

The existing Control Surface EXE remains the normal launcher. It resolves and runs the current `start_control_surface.ps1`.

### A3-M2.1 - Canonical Kadence persona v2

**CLOSED / PHYSICALLY ACCEPTED**

Implementation checkpoints:

- `bff15167dae8dfeea89157917e40d6375afe15b0` - tune persona v2
- `b0cac02bcf912b0b50895213970bd6adf8039e11` - pin persona v2 for LOCAL
- `04b7a2a814346d01bbf294c3a30b28e1559b766c` - restore LOCAL process guard regex
- `1b1518ff7ea0bdc016e63e19c65906b015bf9692` - report canonical identity as v2

Current canonical persona SHA-256:

`f70578920b8360db5a902f417cec426991ea88c0f632cd052b408b4301458166`

Accepted persona direction:

- companion-first, not help-desk
- calm contextual competence
- precise and self-possessed
- restrained dry wit and playful sarcasm
- stable preferences/opinions
- natural British English
- compact spoken answers
- selective warmth
- no habitual AI/server/rack cliches
- utility before performance
- no model-selected physical expression or motion

Persona v2 is now frozen as the working baseline during M3. Do not retune it opportunistically.

## NEXT: A3-M3 - Robot cognition integration

M3 has two separate physical gates.

### M3A - StackChan to LOCAL cognition

Goal:

Route a real spoken StackChan turn through LOCAL `qwen3.5:4b` while retaining the accepted robot transport, ASR, endpointing, session and TTS lifecycle.

Architecture rule:

Do not hard-wire Ollama into robot transport code. Introduce a server-side cognition-provider boundary.

Target shape:

```text
StackChan
   |
   | frozen Xiaozhi/audio path
   v
Kadence backend
   |
   +-- endpointing / ASR / session / TTS
   |
   +-- cognition provider
          +-- LOCAL -> Ollama / qwen3.5:4b
          +-- LUNA  -> accepted remote Luna path
```

The robot should not need to know which provider is active.

First implementation should be server-side. Do not change firmware merely because another design looks cleaner.

M3A physical gate must prove:

1. exact branch/provenance
2. deliberate LOCAL robot mode startup
3. normal StackChan connection
4. normal mic/listening lifecycle
5. real speech transcript reaches LOCAL
6. response exhibits accepted persona v2
7. response returns through existing TTS/robot playback
8. short follow-up context works
9. clean stop/restart
10. no process/port leaks
11. no hidden LUNA fallback
12. no transport regression
13. no firmware change unless separately justified

### M3B - Manual hot LOCAL/LUNA switching

Only begin after M3A is physically accepted.

Goal:

Keep backend server and robot connection alive while the operator changes cognition provider.

Desired behaviour:

```text
SERVER: ONLINE
ROBOT: CONNECTED

COGNITION
[ LOCAL ] [ LUNA ]
```

Rules:

- manual selection only
- LOCAL intended as normal primary
- switch applies at a safe turn boundary
- no server restart solely for provider change
- no robot reconnect solely for provider change
- no AUTO
- no confidence/intelligence threshold
- no silent fallback
- unavailable selected provider must surface as an error

Physical gate must prove repeated LOCAL -> LUNA -> LOCAL real spoken turns while the same server/robot connection remains alive.

## AUTO routing decision

AUTO is intentionally deferred.

Do not ask LOCAL to judge whether a task is "too hard" yet.

Manual switching is currently preferred because it is:

- deterministic
- lower latency
- easier to debug
- predictable for privacy and cost
- immune to false escalation/non-escalation decisions

Reconsider automatic routing only after LOCAL has mature:

- local databases/retrieval
- durable memory
- model training/adaptation where justified
- real-world capability measurements
- confidence/failure telemetry

Only then define evidence-based escalation thresholds.

## Future memory and adaptive interaction wishlist

The objective is to make Kadence feel continuous and attentive without turning all history into permanent prompt clutter.

Preferred later memory design:

- episodic conversation archive
- selectively promoted durable memories
- structured user/project/device facts
- provenance and confidence
- timestamps
- correction/deletion
- selective relevant retrieval

Avoid treating every utterance as equal permanent memory.

Potential later adaptive interaction layer:

- repetition as a possible urgency signal
- terse phrasing as a possible action-first signal
- uncertainty cues as a reason to alter explanation style
- task history to avoid repeating already-proven steps

Do not:

- diagnose anxiety from a pause
- map swear words to fixed emotions
- infer psychological state from one signal
- let tone adaptation override safety/tool boundaries

Long term, LOCAL Kadence should handle most everyday cognition, memory, local data and utility. Luna remains available manually for complex/current/web-heavy work. Specialist delegation or AUTO routing is a later design question.

## Explicitly deferred during M3

Keep out of M3 unless a separate gate is agreed:

- Home Assistant / Tapo writes
- timers
- persistent memory
- generic OS control
- AUTO routing
- intelligence thresholds
- model-driven motion
- extra expressions
- LED behaviour
- permanent fine-tuning
- personality presets
- free-form JSON behaviour UI

## Resume / recovery procedure

Before the next engineering change:

```powershell
cd "C:\AI Project\Project-Kadence-2.0"
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/kadence/2.0-alpha-3
```

Do not reset/stash/delete the known dirty local working state.

Then read:

1. `ALPHA3_FRESH_CHAT_HANDOVER_2026-08-28.md`
2. `ALPHA3_MILESTONES.md`
3. `ALPHA3_LOCAL_VALIDATION.md`
4. `ALPHA3_CONTROL_SURFACE_ENGINE_VALIDATION.md`
5. current `persona/KADENCE_CANONICAL.md`
6. current local hash guard
7. current accepted Xiaozhi backend/provider code

First engineering question:

**Where is the narrowest server-side provider seam that lets the accepted LUNA LLM call be replaced by LOCAL Ollama for a turn without touching robot transport, ASR, endpointing or TTS?**

Answer from the live code before editing.

## Clean-slate development rules

- one milestone at a time
- one physical gate at a time
- exact commit anchors
- no physical acceptance claims without operator evidence
- no opportunistic persona retuning
- no firmware churn without evidence
- no AUTO routing
- no silent fallback
- preserve rollback paths
- document each accepted gate immediately

This snapshot is the current Alpha 3 recovery and resume document.
