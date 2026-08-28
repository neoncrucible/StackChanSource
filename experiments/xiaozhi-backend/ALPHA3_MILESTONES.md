# Project Kadence 2.0 - Alpha 3 Milestones

Updated: 28 Aug 2026

This file is the Alpha 3 milestone index. It does not reopen or renumber frozen Alpha 2 milestones.

Latest code/persona anchor before this documentation refresh:

`1b1518ff7ea0bdc016e63e19c65906b015bf9692`

## A3-M1 - LOCAL standalone inference

**Status: CLOSED / PHYSICALLY ACCEPTED**

Scope:

- Project-owned Ollama runtime on Windows;
- `qwen3.5:4b` baseline candidate;
- canonical Kadence persona supplied at request time;
- factual and personality responses;
- clean stop / restart;
- no TCP 11434 leak;
- 100% GPU placement on the target RTX 3060 Laptop GPU.

Validation source:

- `ALPHA3_LOCAL_VALIDATION.md`

Accepted checkpoint:

`a5af604eca1c356bcfe1094392c85f71e604543e`

## A3-M2 - Explicit LOCAL / LUNA Control Surface

**Status: CLOSED / PHYSICALLY ACCEPTED**

Scope:

- explicit LOCAL / LUNA selection before start;
- no AUTO mode;
- START launches only the selected engine;
- STOP cleans only the selected engine;
- LOCAL Control Surface chat;
- LUNA Control Surface chat;
- short multi-turn context on both paths;
- quiet Enter-to-send;
- correct UTF-8 rendering for LUNA responses;
- LOCAL failure surfaces with no LUNA fallback;
- LUNA failure surfaces with no LOCAL fallback;
- frozen Alpha 2 transport and firmware invariants remain untouched.

Validation sources:

- `ALPHA3_CONTROL_SURFACE_LOCAL_VALIDATION.md`
- `ALPHA3_CONTROL_SURFACE_ENGINE_VALIDATION.md`

Accepted milestone closure checkpoint:

`06b3b61669fa3fc3a6041e73613dccffdbdbd63b`

## A3-M2.1 - Canonical Kadence persona v2

**Status: CLOSED / PHYSICALLY ACCEPTED**

The LOCAL personality baseline was deliberately refined after M2 and then extensively exercised in normal conversation before acceptance.

Accepted identity properties include:

- companion-first rather than help-desk framing;
- calm contextual competence;
- precision and emotional restraint;
- sharp, sparse dry wit and playful sarcasm;
- stable preferences and opinions where appropriate;
- natural British English and compact spoken delivery;
- selective warmth without therapy-script reassurance;
- no habitual AI/server/rack/programming cliches;
- no model-selected robot motion, servo coordinates, LED behaviour or physical expressions.

Implementation checkpoints:

- `bff15167dae8dfeea89157917e40d6375afe15b0` - tune Kadence companion persona v2;
- `b0cac02bcf912b0b50895213970bd6adf8039e11` - pin persona v2 for LOCAL runtime;
- `04b7a2a814346d01bbf294c3a30b28e1559b766c` - restore LOCAL runtime ownership guard regex;
- `1b1518ff7ea0bdc016e63e19c65906b015bf9692` - report canonical identity as v2.

Current canonical persona SHA-256:

`f70578920b8360db5a902f417cec426991ea88c0f632cd052b408b4301458166`

Persona v2 is now the accepted baseline. Do not casually retune it while implementing transport, routing, memory or utility work. Reopen personality only for a specific repeatable behavioural defect or a deliberately scoped later milestone.

## A3-M3 - Robot cognition integration and manual hot switching

**Status: NEXT / NOT STARTED**

M3 is deliberately split into two physical gates.

### A3-M3A - StackChan -> LOCAL cognition

Goal:

Route a real StackChan spoken turn through the accepted LOCAL cognition path while preserving the frozen Alpha 2 robot transport and audio lifecycle.

The implementation should introduce a clear cognition-provider boundary rather than hard-wire Ollama directly into robot transport code. This boundary is required so later provider switching does not require a robot reconnect or transport rewrite.

Must preserve:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- accepted OpenAI Realtime ASR path unless a separately agreed later milestone changes ASR;
- Windows Silero endpointing / 700 ms sustained-silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot-owned mic stop, final flush and playback lifecycle;
- accepted firmware behaviour and EYE geometry;
- Sonia Edge TTS path;
- safe tool boundary;
- no model-driven motion.

Physical acceptance must prove at minimum:

1. server starts deliberately in LOCAL cognition mode;
2. StackChan connects through the existing transport;
3. one real spoken turn reaches LOCAL `qwen3.5:4b`;
4. response returns through the existing robot TTS/playback path;
5. short follow-up context works;
6. stop/restart works without process or port leaks;
7. frozen LUNA path is not silently invoked;
8. no firmware change is required unless new physical evidence proves one necessary.

### A3-M3B - Manual LOCAL / LUNA hot switch while server remains online

Goal:

Allow the operator to change the cognition provider while the backend server and StackChan connection remain alive.

Required behaviour:

- explicit manual `LOCAL` / `LUNA` selector only;
- LOCAL is intended to become the normal primary engine;
- changing provider applies to the next safe conversational turn;
- no server restart solely to change cognition provider;
- no robot reconnect solely to change cognition provider;
- no AUTO mode;
- no confidence threshold or self-routing logic;
- no silent fallback in either direction;
- an unavailable selected provider must surface as an error rather than silently using the other provider.

Physical acceptance must prove repeated LOCAL -> LUNA -> LOCAL switching across real robot turns with the transport staying connected.

## Later local-first architecture - deliberately deferred

The long-term direction is LOCAL Kadence doing most day-to-day work, with Luna used deliberately for web-heavy, complex or otherwise remote tasks.

Automatic escalation is **not** part of M3. Intelligence thresholds are intentionally deferred until LOCAL has enough real-world evidence behind it.

Before AUTO routing is reconsidered, the project should first mature:

- persistent local databases / retrieval;
- durable memory with correction and deletion;
- model training or adaptation work where justified;
- real measurements of LOCAL capability boundaries;
- explicit failure and confidence telemetry.

Only then should an AUTO-routing milestone define evidence-based escalation criteria. Until that point, manual switching is the accepted design because it is faster, predictable, privacy-preserving and easy to debug.

## Future memory / interaction wishlist - parked, not claimed

A later memory foundation may include:

- episodic conversation archive;
- selectively promoted durable memories;
- structured user/project/device facts;
- provenance, confidence, timestamps and correction/deletion;
- retrieval that injects only relevant context instead of entire histories.

A later adaptive interaction layer may use soft signals such as repetition, urgency and uncertainty to alter response brevity or delivery. It must not diagnose emotional state from single signals, and it must never override safety or capability boundaries.

## Deferred beyond current milestone

Still deferred unless separately agreed and gated:

- Home Assistant / Tapo writes;
- timers;
- persistent memory;
- generic OS control;
- AUTO routing;
- model-driven motion;
- additional expressions or LED behaviour;
- permanent fine-tuning;
- personality preset systems;
- JSON tuning/profile UI.
