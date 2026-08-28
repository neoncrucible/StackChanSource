# Project Kadence 2.0 - Alpha 3 Clean-Slate Handover

Prepared: 28 Aug 2026  
Repository: `neoncrucible/StackChanSource`  
Active branch: `kadence/2.0-alpha-3`  
Active Windows repo: `C:\AI Project\Project-Kadence-2.0`

## 1. Purpose

This handover is the single restart point for the next Project Kadence 2.0 work session.

It replaces fragmented chat context with one current source of truth. It is based on:

- the live `kadence/2.0-alpha-3` GitHub branch;
- the operator's physical Windows repository state captured on 28 Aug 2026;
- the physically accepted Alpha 3 LOCAL and Control Surface gates;
- the accepted Kadence canonical persona v2 refinement;
- the newly agreed M3 architecture: robot LOCAL integration first, then manual hot LOCAL/LUNA switching while the server remains online.

Do not infer newer behaviour from older chats if it conflicts with this handover or the live branch.

---

## 2. Ground-truth repository state

At the operator's 28 Aug 2026 inspection, local and remote were identical:

- local HEAD: `1b1518ff7ea0bdc016e63e19c65906b015bf9692`
- remote `origin/kadence/2.0-alpha-3`: `1b1518ff7ea0bdc016e63e19c65906b015bf9692`
- branch: `kadence/2.0-alpha-3`

That code/persona anchor contains the accepted persona-v2 implementation and local runtime guard restoration.

Documentation refresh committed after that code anchor:

- `3e642e7a16091dac89fef63219b95e9154a1ce4f` - update Alpha 3 roadmap after persona v2 acceptance.

The operator's local checkout will therefore need a normal fast-forward pull before the next work session after these documentation commits are complete.

### Preserved dirty working tree

The local repository is intentionally **not clean**. Do not reset, stash, delete or overwrite these without a specific reason:

Modified:

- `firmware/fetch_repos.py`
- `firmware/tools/apply_m6_pixel_weather_display.py`

Untracked / generated:

- `experiments/xiaozhi-backend/.tools/`
- `experiments/xiaozhi-backend/__pycache__/`
- generated `control_surface/KadenceControl-run-*.ps1` files
- `experiments/xiaozhi-backend/tmp/`

These were present while local HEAD still matched the remote branch. Treat them as local working/runtime state, not evidence that the branch itself is out of date.

---

## 3. Windows project layout that matters

The active project root is:

`C:\AI Project\Project-Kadence-2.0`

Relevant neighbouring paths include:

- `C:\AI Project\Archive\...` - historical material only; do not accidentally resume development here.
- `C:\AI Project\Kadence-2.0-flash` - separate flash workspace.
- `C:\AI Project\Kadence-Flash\M6-Pixel-Weather-995a255` - accepted M6 firmware flash checkpoint.
- `C:\AI Project\Project-Kadence-2.0\docs\checkpoints` - checkpoint documents.
- `C:\AI Project\Project-Kadence-2.0\experiments\xiaozhi-backend` - active Windows backend/control work.
- `...\experiments\xiaozhi-backend\.runtime\local\ollama\models` - LOCAL Ollama model store.
- `...\experiments\xiaozhi-backend\.runtime\xiaozhi-esp32-server` - materialized/pinned Xiaozhi backend runtime.
- `...\experiments\xiaozhi-backend\control_surface` - Control Surface source/patch chain.
- `...\experiments\xiaozhi-backend\persona` - canonical Kadence identity source.
- `C:\AI Project\Project-Kadence-2.0\firmware` - firmware source; frozen transport/firmware invariants apply.

Do not use a similarly named historical repo under `Archive` as the active source tree.

---

## 4. Frozen Alpha 2 baseline - do not reopen casually

Frozen branch:

`kadence/2.0-alpha-2`

Closure/documentation head:

`c74d8949f33c6dea1d7df2bea248cad9e82d5dd1`

Final physically accepted Alpha 2 runtime/source anchor:

`348e7c0fc05a027ba9affc7677534e488bd338c9`

Other accepted anchors:

- M6 backend validation: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- M6 pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`
- frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- physically validated Alpha 1 firmware: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- independent rollback line: `beta/project-kadence`
- pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`

### Frozen transport invariants

Preserve unless new physical evidence forces a deliberate reopen:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime ASR on the accepted LUNA/robot path;
- Windows Silero preferred endpointing;
- 700 ms sustained-silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot-owned microphone stop/final-flush/playback lifecycle;
- versioned Project-owned control messages;
- no model-selected arbitrary robot motion.

### Frozen Alpha 2 capability baseline

Keep these working while Alpha 3 evolves:

- Sonia Edge TTS;
- process-lifetime short conversational continuity;
- safe allow-listed tool boundary;
- M6 read-only tools:
  - `kadence_datetime`
  - `kadence_weather`
  - `kadence_web_lookup`
- trusted weather icon enum:
  - `clear`
  - `cloud`
  - `rain`
  - `snow`
- accepted M6-era Control Surface visual base;
- EYE scaled to 90 percent and recentered;
- retired M7 DEFAULT/CUSTOM behaviour overlay remains retired.

No AUTO routing and no silent provider fallback.

---

## 5. Alpha 3 accepted work

### A3-M1 - LOCAL standalone inference

**CLOSED / PHYSICALLY ACCEPTED**

Accepted runtime:

- Ollama for Windows;
- model baseline `qwen3.5:4b`;
- model size about 3.3 GB;
- target GPU NVIDIA RTX 3060 Laptop 6 GB;
- observed 100 percent GPU placement;
- context 8192.

Accepted behaviour:

- Project-owned `ollama serve`;
- explicit process and TCP 11434 ownership checks;
- factual responses;
- Kadence personality response;
- clean stop;
- restart;
- no listener/process leak.

Validation:

`experiments/xiaozhi-backend/ALPHA3_LOCAL_VALIDATION.md`

Accepted checkpoint:

`a5af604eca1c356bcfe1094392c85f71e604543e`

### A3-M2 - Explicit LOCAL/LUNA Control Surface

**CLOSED / PHYSICALLY ACCEPTED**

Accepted behaviour:

- explicit LOCAL or LUNA selection;
- no AUTO;
- selected engine is obvious before start;
- START launches only selected path;
- STOP cleans selected path;
- LOCAL text chat;
- LUNA text chat;
- short multi-turn context on both;
- quiet Enter-to-send;
- explicit UTF-8 decoding on LUNA;
- no mojibake in validated punctuation;
- LOCAL conflict on 11434 fails closed with no LUNA start;
- LUNA conflict on 8000 fails closed with no LOCAL start;
- Alpha 2 LUNA backend still launches;
- no committed firmware delta required for this slice.

Validation:

- `ALPHA3_CONTROL_SURFACE_LOCAL_VALIDATION.md`
- `ALPHA3_CONTROL_SURFACE_ENGINE_VALIDATION.md`

Accepted closure checkpoint:

`06b3b61669fa3fc3a6041e73613dccffdbdbd63b`

The existing Control Surface EXE remains a launcher wrapper that resolves `start_control_surface.ps1`, so the normal operator path remains: launch EXE, choose engine, START.

---

## 6. Accepted Kadence canonical persona v2

**CLOSED / PHYSICALLY ACCEPTED AS THE CURRENT PERSONALITY BASELINE**

The operator extensively tested persona v2 in ordinary conversation on 27 Aug 2026 and explicitly accepted it as the desired Kadence personality.

Persona implementation sequence:

- `bff15167dae8dfeea89157917e40d6375afe15b0` - tune Kadence companion persona v2;
- `b0cac02bcf912b0b50895213970bd6adf8039e11` - pin persona v2 for LOCAL runtime;
- `04b7a2a814346d01bbf294c3a30b28e1559b766c` - restore LOCAL Ollama ownership guard regex;
- `1b1518ff7ea0bdc016e63e19c65906b015bf9692` - report canonical identity as v2.

Current canonical persona SHA-256:

`f70578920b8360db5a902f417cec426991ea88c0f632cd052b408b4301458166`

Accepted character direction:

- capable long-term companion rather than help-desk agent;
- calm contextual intelligence;
- precision and emotional economy;
- sharp but sparse wit;
- playful sarcasm when useful;
- stable preferences/opinions for subjective questions;
- natural British English;
- compact spoken delivery;
- selective warmth rather than default reassurance;
- no habitual server/rack/programming/robot cliches;
- utility before performance;
- no model-selected robot movement or physical expression.

### Freeze rule

Do not keep retuning persona v2 while doing M3.

Reopen personality only if:

1. a specific repeatable behavioural defect appears; or
2. a later deliberately scoped personality/adaptation milestone is agreed.

This prevents transport/routing work from becoming entangled with subjective persona changes.

---

## 7. NEXT: A3-M3 - robot cognition integration

M3 is now split into two gates.

The architectural principle is important:

**Do not hard-wire Ollama into robot transport code. Introduce a cognition-provider boundary inside the backend so the robot transport can remain stable while the selected brain changes.**

Target shape:

```text
StackChan
   |
   | frozen Xiaozhi/audio transport
   v
Kadence backend
   |
   +-- endpointing / ASR / session / TTS
   |
   +-- cognition provider
          |
          +-- LOCAL -> qwen3.5:4b / Ollama
          |
          +-- LUNA  -> accepted GPT-5.6 Luna path
```

The robot should not need to know which cognition provider is active.

### A3-M3A - StackChan -> LOCAL through frozen transport

**NEXT IMPLEMENTATION SLICE**

Objective:

Prove one real StackChan voice turn reaches LOCAL `qwen3.5:4b` and returns to the robot speaker without changing the physically accepted transport lifecycle.

Implementation bias:

- reuse the existing Xiaozhi server;
- keep ASR, endpointing, Opus transport and TTS stable;
- change only the cognition provider boundary required to send completed user text to LOCAL;
- preserve Luna as a separate explicit provider;
- prefer server-side changes before firmware changes;
- do not flash firmware merely because another implementation looks cleaner.

Minimum physical gate:

1. exact branch/provenance check;
2. server starts in deliberate LOCAL robot mode;
3. StackChan connects normally;
4. existing microphone/listening lifecycle behaves normally;
5. real spoken transcript reaches LOCAL;
6. LOCAL response is recognisably persona v2;
7. response returns through Sonia/accepted robot playback;
8. short follow-up context works;
9. stop and restart cleanly;
10. no port/process leaks;
11. no hidden LUNA call/fallback;
12. no transport regression;
13. no firmware change unless separately justified by physical evidence.

### A3-M3B - Manual hot LOCAL/LUNA switch with server online

**AFTER M3A PASSES**

Objective:

Allow the operator to change the cognition provider while the backend server remains up and StackChan remains connected.

Desired Control Surface behaviour:

```text
SERVER: ONLINE
ROBOT: CONNECTED

COGNITION
[ LOCAL ] [ LUNA ]
```

Required semantics:

- explicit manual selection only;
- LOCAL intended as normal primary engine;
- switch applies at a safe turn boundary;
- server does not restart just to change provider;
- robot does not reconnect just to change provider;
- no AUTO mode;
- no self-assessed intelligence threshold;
- no silent fallback;
- if selected provider is unavailable, surface that failure.

Minimum physical gate:

- LOCAL spoken turn passes;
- switch to LUNA while server/robot stay connected;
- LUNA spoken turn passes;
- switch back to LOCAL while server/robot stay connected;
- second LOCAL spoken turn passes;
- continuity/turn ownership remains sane;
- failure tests prove no fallback in either direction.

Do not claim M3B accepted from Control Surface text-chat switching. This gate specifically requires real robot voice turns while the same server connection remains alive.

---

## 8. Why AUTO routing is deferred

Do not build intelligence thresholds yet.

Current design decision:

**Manual provider selection is the accepted design until the LOCAL stack has mature databases, memory/retrieval, training/adaptation and enough real usage to measure what it can and cannot do.**

Reasons:

- deterministic;
- lower debugging complexity;
- lower latency;
- predictable privacy/cost;
- no false "this task is too hard" classification;
- no local model pretending to know its own capability boundary;
- easier physical validation.

Only reconsider AUTO after there is evidence for:

- current/live web requirements;
- external specialist tool requirements;
- context limits;
- measured local failure patterns;
- confidence/quality telemetry;
- explicit user override.

No AUTO work belongs in M3.

---

## 9. Future Kadence wishlist - parked for later

A hypothetical Kadence wishlist proposed:

- persistent user/profile storage;
- long-term context integration;
- adaptive response style based on interaction signals.

The objective is useful, but the literal first draft should not be implemented unchanged.

### Future persistent memory foundation

Prefer:

- episodic conversation archive;
- selectively promoted durable memories;
- structured facts/preferences/projects/devices;
- provenance;
- confidence;
- timestamps;
- correction and deletion;
- selective retrieval rather than dumping lifetime history into every prompt.

Do not permanently embed every utterance as equally important memory.

### Future adaptive interaction layer

Potential soft signals:

- repeated question -> possible urgency;
- terse/repeated phrasing -> possible action-first preference;
- hesitation/uncertainty cues -> possibly gentler explanation;
- current task history -> avoid repeating already-proven steps.

Do not:

- diagnose anxiety from a five-second pause;
- treat swear words as fixed emotional labels;
- infer psychological state from one signal;
- let style calibration override safety/tool boundaries.

### Long-term architecture direction

LOCAL Kadence should eventually do most day-to-day cognition, memory, local databases and utility.

Luna should remain available manually for complex/current/web-heavy tasks.

Later, after LOCAL capability is mature, Luna may become an explicit specialist delegate. That is a future design question, not current M3 scope.

---

## 10. Explicitly deferred

Unless a new milestone is agreed, keep these out of M3:

- Home Assistant / Tapo writes;
- timers;
- persistent memory;
- generic OS control;
- AUTO provider routing;
- intelligence-threshold classification;
- model-driven motion;
- additional expressions;
- LED behaviour;
- permanent fine-tuning;
- personality preset system;
- free-form JSON behaviour/profile UI.

Do not resurrect the retired M7 behaviour overlay.

---

## 11. Next-chat startup procedure

The next chat should begin from this handover and the live branch, not from remembered snippets.

First terminal checks:

```powershell
cd "C:\AI Project\Project-Kadence-2.0"
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/kadence/2.0-alpha-3
```

Do not reset/stash/delete the known dirty working tree.

After pulling the documentation refresh, the next assistant should:

1. read this handover;
2. read `ALPHA3_MILESTONES.md`;
3. read the current M1/M2 validation docs;
4. read current persona v2 and hash guard;
5. inspect the live Alpha 2 backend/provider path before proposing code;
6. identify the narrowest provider seam for M3A;
7. propose the M3A physical gate before editing;
8. make no firmware change in the first slice unless physical evidence requires it.

### Immediate next engineering question

**Where is the narrowest server-side boundary in the pinned/accepted Xiaozhi backend where the existing LUNA LLM provider can be replaced by LOCAL Ollama for a turn without changing robot transport, ASR, endpointing or TTS?**

Answer that from the live code before implementing anything.

---

## 12. Clean-slate rule

For the next batch of work:

- one milestone at a time;
- one physical gate at a time;
- exact commit anchors;
- no claims of validation without operator evidence;
- no opportunistic persona changes;
- no firmware churn without evidence;
- no AUTO routing;
- no silent fallback;
- preserve rollback points;
- document accepted physical state immediately after each gate.

That is the current Project Kadence 2.0 Alpha 3 source of truth.
