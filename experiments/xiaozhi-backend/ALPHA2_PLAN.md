# Kadence 2.0 Alpha 2 — Current Plan

Status: **PAUSED AT M6 / M7 RETIRED / M8 NOT STARTED**

Date updated: **23 Aug 2026**  
Branch: `kadence/2.0-alpha-2`

## Proven anchors

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- Independent rollback line: `beta/project-kadence`
- M6 final backend behaviour checkpoint: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- M6 physically accepted pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`

## Active Alpha 2 feature state

Alpha 2 currently stops at the proven M6 capability set:

- canonical Kadence identity;
- GPT-5.6 Luna only, `reasoning_effort: none`;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- Sonia Edge TTS;
- M4 bounded process-lifetime conversation continuity;
- M5 Project-owned safe allow-listed tool boundary;
- M6 read-only utilities:
  - `kadence_datetime`
  - `kadence_weather`
  - `kadence_web_lookup`
- trusted static weather display enum only: `clear | cloud | rain | snow`;
- M6-era Control Surface, with the EYE scaled to 90% and recentred so it does not overlap/clamp the panel.

## Frozen transport invariants

Do not silently retune:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- Windows Silero endpointing with 700 ms sustained-silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot authority over microphone stop/final flush/playback lifecycle;
- versioned Project-owned `type:"kadence"` messages;
- no raw model-generated servo coordinates;
- no secrets or personal memory committed to Git.

## Milestone status

- **M0** — scope/provenance: PASS / CLOSED
- **M1** — canonical identity: PASS / CLOSED
- **M2** — Control Surface foundation: USER ACCEPTED / CLOSED
- **M3** — provider benchmark: PASS / CLOSED / HISTORICAL; Luna selected
- **M4** — volatile session continuity: PASS / CLOSED
- **M5** — safe tool boundary: PASS / CLOSED
- **M6** — first read-only utilities + pixel weather display: PASS / CLOSED
- **M7** — DEFAULT/CUSTOM behaviour overlay: **RETIRED / SUPERSEDED**
- **M8** — final mixed acceptance/freeze: **NOT STARTED / PAUSED**

Canonical M6 record: `MILESTONE6_VALIDATION.md`.
M7 retirement record: `MILESTONE7_VALIDATION.md`.

## M7 retirement decision

The temporary free-text CUSTOM behaviour overlay is not part of active Alpha 2.

The active launcher removes any previously applied M7 runtime hooks before restoring the proven M6 tool path. The active Control Surface does not render the M7 behaviour card or reserve port 8766.

Historical M7 source/commits remain in Git only as experimental evidence.

## Future cognition/personality direction

The intended future selector remains exactly:

- `LOCAL`
- `LUNA`

No AUTO mode and no silent fallback.

Custom personality/profile behaviour is parked with the future **LOCAL** inference work. The current direction is to make custom personality a local-model/profile capability rather than layering additional behaviour instructions over normal Luna operation.

That work is outside the current Alpha 2 pause point and requires a new explicit scope decision before implementation.

## Explicitly out of scope while paused

- M7 prompt overlay reactivation;
- persistent memory;
- timers/reminders;
- smart-home/device writes;
- arbitrary OS control;
- local LLM deployment;
- LOCAL/LUNA switching;
- AUTO routing;
- new robot expressions/motion;
- transport/endpoint retuning without new physical evidence.

## Resume instruction

When work resumes, treat M0-M6 as closed and M7 as retired. Start from the active M6 runtime/UI state, not from the historical M7 implementation. Decide explicitly whether to finish/freeze Alpha 2 at M6 or open a new post-Alpha-2/local-inference milestone.
