# Project Kadence 2.0 — Alpha 3 Milestones

Updated: 24 Aug 2026

This file is the Alpha 3 milestone index. It does not reopen or renumber frozen Alpha 2 milestones.

## A3-M1 — LOCAL standalone inference

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

## A3-M2 — Explicit LOCAL / LUNA Control Surface

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

## A3-M3 — LOCAL robot integration

**Status: NEXT / NOT STARTED**

Goal:

Connect the physically accepted LOCAL cognition path to StackChan while preserving the frozen Alpha 2 robot transport invariants.

First implementation slice must not silently alter:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus uplink;
- OpenAI Realtime ASR path used by accepted LUNA operation;
- Silero endpointing / 700 ms silence hold;
- robot-owned mic stop, final flush, and playback lifecycle;
- accepted firmware behaviour or EYE geometry.

A3-M3 must have its own physical validation before any later Alpha 3 capability work is treated as accepted.

## Deferred beyond current milestone

Still deferred unless separately agreed and gated:

- Home Assistant / Tapo;
- timers;
- persistent memory;
- OS control;
- AUTO routing;
- motion;
- additional expressions or LED behaviour;
- permanent fine-tuning;
- personality preset systems;
- JSON tuning/profile UI.
