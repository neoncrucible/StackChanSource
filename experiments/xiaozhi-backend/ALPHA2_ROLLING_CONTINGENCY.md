# Project Kadence 2.0 — Alpha 2 Rolling Contingency Snapshot

**Status:** M0-M6 CLOSED / M7 RETIRED / PROJECT PAUSED BEFORE M8  
**Snapshot:** 23 Aug 2026, Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Active branch:** `kadence/2.0-alpha-2`

## Proven anchors

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- Independent rollback line: `beta/project-kadence`
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- M6 final backend behaviour checkpoint: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- M6 physically accepted pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`

## Active runtime state

The active Alpha 2 launcher now deliberately restores the M6 architecture:

- canonical Kadence persona;
- GPT-5.6 Luna only / reasoning none;
- OpenAI Realtime ASR;
- Sonia Edge TTS;
- M4 volatile session continuity;
- M5 safe tool authority boundary;
- M6 read-only tools only: date/time, weather, factual web lookup;
- no M7 CUSTOM behaviour overlay;
- no loopback behaviour-control server;
- no port 8766 requirement;
- no persistent memory or arbitrary execution.

If the ignored local runtime was previously modified by M7, `remove_m7_behavior_windows.ps1` removes only the M7 hooks before the original M6 tool applier runs.

## Control Surface state

The active Control Surface is the M6-era V4/V4.1/V4.3 render path.

The only retained post-M6 visual repair is the EYE geometry fix:

- scaled to 90%;
- recentred in the 280 px left panel;
- no M7 SESSION BEHAVIOUR card;
- no CUSTOM/APPLY CUSTOM controls.

## Milestones

- M0 scope/provenance — CLOSED
- M1 canonical identity — CLOSED
- M2 Control Surface foundation — CLOSED
- M3 provider benchmark — CLOSED / historical
- M4 volatile session continuity — CLOSED
- M5 safe tool boundary — CLOSED
- M6 first utilities / pixel weather — CLOSED
- M7 behaviour overlay — **RETIRED / SUPERSEDED**
- M8 final acceptance/freeze — **NOT STARTED**

`MILESTONE7_VALIDATION.md` is now a retirement record, not an active validation claim.

## M7 retirement rationale

The free-text behaviour-overlay experiment is no longer worth carrying in normal Luna operation. Later physical testing showed inconsistent end-to-end behaviour application and a UI regression during follow-on iteration. The user explicitly chose to remove the feature rather than continue debugging it.

Historical source/commits remain available in Git, but M7 must not be silently re-enabled.

## Future direction

Future cognition selector remains:

- `LOCAL`
- `LUNA`

No AUTO mode and no silent fallback.

Custom personality/profile work is parked with LOCAL inference. The current direction is for custom personality to be a local model/profile capability rather than an additional instruction injected into ordinary Luna conversations.

## Frozen transport invariants

Do not alter without new physical evidence and explicit reopening:

- Xiaozhi v1 WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime ASR;
- 700 ms Windows Silero silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot-owned microphone/playback lifecycle;
- versioned Project-owned control messages.

## Resume instruction

On resume, read this snapshot, `ALPHA2_PLAN.md`, `MILESTONE6_VALIDATION.md` and the M7 retirement record. Treat M0-M6 as closed, M7 as retired, and the project as paused before M8. Do not restart M7 work unless the user explicitly reopens it. For custom personality, prefer the future LOCAL milestone rather than normal Luna prompt overlays.
