# Kadence 2.0 Alpha 2 — Milestone 7 Retirement Record

Status: **RETIRED / SUPERSEDED / NOT PART OF ACTIVE ALPHA 2**

Date retired: **23 Aug 2026**  
Branch: `kadence/2.0-alpha-2`

## Decision

The DEFAULT/CUSTOM volatile behaviour-overlay experiment is no longer part of the active Alpha 2 architecture.

Physical testing proved the loopback control concept could work, but subsequent testing exposed inconsistent end-to-end behaviour application and a Control Surface regression during later UI iteration. Rather than continue layering temporary prompt instructions onto normal Luna operation, the user chose to return Alpha 2 to the proven M6 feature set.

## Active replacement state

Active Alpha 2 returns to:

- canonical Kadence persona only;
- GPT-5.6 Luna only;
- M4 volatile session continuity;
- M5 safe tool boundary;
- M6 read-only utilities (`kadence_datetime`, `kadence_weather`, `kadence_web_lookup`);
- physically accepted M6 pixel-weather firmware `995a2556f42e030660d6ed651b782987ac4a3d8e`;
- M6-era Control Surface, with only the later 90%-scaled/recentred EYE geometry fix retained.

The active launcher explicitly removes any previously applied M7 hooks from the ignored local runtime before restoring the proven M6 tool path.

## Future direction

Custom personality behaviour is parked for the future **LOCAL / LUNA** architecture. The intended direction is to make custom personality/profile behaviour part of the local inference mode rather than injecting an additional behaviour prompt into ordinary Luna use.

No AUTO routing or silent fallback is implied by this decision.

## Historical note

M7 implementation files and commits remain in Git history as experimental evidence. They are not active runtime capability and should not be re-enabled implicitly.

Any future custom-personality work requires a new explicit scope decision.
