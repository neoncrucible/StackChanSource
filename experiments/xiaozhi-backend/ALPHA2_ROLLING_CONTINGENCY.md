# Project Kadence 2.0 — Alpha 2 Final Recovery Snapshot

**Status:** VALIDATED / FROZEN / BRANCH CLOSED  
**Snapshot:** 23 Aug 2026, Europe/London  
**Repository:** `neoncrucible/StackChanSource`  
**Frozen branch:** `kadence/2.0-alpha-2`

## Final acceptance anchors

- Final physically accepted runtime/source state: `348e7c0fc05a027ba9affc7677534e488bd338c9`
- Final validation record: `ALPHA2_FINAL_VALIDATION.md`
- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- Independent rollback line: `beta/project-kadence`
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- M6 backend validation checkpoint: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- Physically accepted M6 pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`

The final physical run was performed at `348e7c0...`. Later commits on this branch are documentation-only closure records and must not be confused with the physically exercised runtime state.

## Frozen active feature state

Final Alpha 2 contains:

- canonical Kadence persona;
- GPT-5.6 Luna only / reasoning none;
- OpenAI Realtime ASR;
- Sonia Edge TTS;
- M4 volatile process-lifetime session continuity;
- M5 safe tool authority boundary;
- M6 read-only tools only:
  - `kadence_datetime`
  - `kadence_weather`
  - `kadence_web_lookup`
- trusted static pixel weather display enum only: `clear | cloud | rain | snow`;
- M6-era Control Surface with the later 90%-scale/recenter EYE geometry repair.

No persistent memory, generic OS execution, unrestricted MCP/IoT path, smart-home writes, model-driven motion, provider fallback or active custom behaviour overlay exists.

## Final physical smoke after M7 retirement

The final physical session demonstrated:

- the M6-era Control Surface launched normally;
- M7 loopback control, prompt overlay and runtime helper were explicitly removed from the ignored local runtime;
- canonical identity and Luna profile loaded correctly;
- M5 and M6 patch/application paths remained clean and idempotent;
- pinned upstream was verified;
- robot connected over the frozen Xiaozhi v1 transport;
- 16 kHz / 60 ms Opus negotiation remained intact;
- OpenAI Realtime ASR reported ready with the accepted 700 ms endpoint hold;
- tool advertisement contained exactly the three M6 utilities;
- a weather request for East Cowes executed `kadence_weather`;
- trusted `weather_icon=clear` UI output was emitted;
- the spoken weather response completed successfully through TTS.

Backend CI was green at the final physical runtime checkpoint. The physically accepted firmware remains the dedicated green/flashed checkpoint `995a255...`.

## Milestone disposition

- M0 — CLOSED
- M1 — CLOSED
- M2 — CLOSED
- M3 — CLOSED / historical
- M4 — CLOSED
- M5 — CLOSED
- M6 — CLOSED
- M7 — RETIRED / SUPERSEDED; excluded from final Alpha 2
- M8 — PASS / CLOSED; final assembled-state acceptance and freeze

`MILESTONE7_VALIDATION.md` is a retirement record, not an active capability claim.

## M7 retirement rationale

The free-text Luna behaviour-overlay experiment was deliberately abandoned. Later physical testing showed inconsistent end-to-end behaviour application and a follow-on Control Surface regression. The user chose to return to the proven M6 architecture rather than continue adding prompt-overlay complexity.

Final startup therefore removes any prior M7 runtime hooks and returns to the original M6 tool path. Historical M7 source remains in Git only as experimental evidence.

Custom personality/profile work is parked with future LOCAL inference work.

## Accepted known limitations

- Broad/ambiguous geographic names may resolve to a same-named locality before Kadence identifies the ambiguity and asks for a more specific place. Specific city/place weather queries are the intended Alpha 2 path and this limitation is accepted.
- Previously observed chat-title `NoneType` and missing-close-frame warnings were teardown noise around client disconnect/reconnect and were non-blocking.
- One long spoken answer was followed by a robot/client disconnect after TTS completion; it was not reproduced sufficiently to justify reopening transport.

## Frozen transport invariants

Do not alter this branch without an explicit historical reopen:

- Xiaozhi v1 WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime ASR;
- 700 ms Windows Silero silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot-owned microphone/final-flush/playback lifecycle;
- versioned Project-owned control messages.

## Future direction / resume rule

Alpha 2 is finished. Do not resume normal development on this branch.

Future work must branch from this frozen state. The intended later cognition selector remains exactly `LOCAL / LUNA`, with no AUTO mode and no silent fallback. Custom personality/profile behaviour belongs with future LOCAL inference rather than Luna prompt overlays.

Alpha 3 should contain a small number of meaningful architectural/user-visible upgrades. Beta should then focus mainly on incremental utility expansion and real-world hardening before everyday use.
