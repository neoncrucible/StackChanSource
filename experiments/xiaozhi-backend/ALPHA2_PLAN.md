# Kadence 2.0 Alpha 2 — Final Plan / Freeze Record

Status: **VALIDATED / FROZEN / BRANCH CLOSED**

Date closed: **23 Aug 2026**  
Branch: `kadence/2.0-alpha-2`

## Final accepted anchors

- Final physically accepted runtime/source state: `348e7c0fc05a027ba9affc7677534e488bd338c9`
- Final Alpha 2 validation record: `ALPHA2_FINAL_VALIDATION.md`
- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- Independent rollback line: `beta/project-kadence`
- M6 backend validation checkpoint: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`
- Physically accepted pixel-weather firmware: `995a2556f42e030660d6ed651b782987ac4a3d8e`

Documentation commits after `348e7c0...` are closure bookkeeping only and are not separately claimed as physically tested runtime states.

## Final Alpha 2 capability set

Alpha 2 closes on the proven M6 architecture plus the isolated Control Surface EYE geometry repair:

- canonical Project-owned Kadence identity;
- GPT-5.6 Luna only / `reasoning_effort: none`;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- Sonia Edge TTS;
- M4 bounded process-lifetime conversation continuity;
- M5 Project-owned safe allow-listed tool boundary;
- M6 read-only utilities:
  - `kadence_datetime`
  - `kadence_weather`
  - `kadence_web_lookup`
- trusted static weather enum only: `clear | cloud | rain | snow`;
- physically accepted pixel weather display;
- M6-era Control Surface with the EYE scaled to 90% and recentered.

## Milestone disposition

- **M0** — PASS / CLOSED
- **M1** — PASS / CLOSED
- **M2** — USER ACCEPTED / CLOSED
- **M3** — PASS / CLOSED / HISTORICAL; Luna selected
- **M4** — PASS / CLOSED
- **M5** — PASS / CLOSED
- **M6** — PASS / CLOSED
- **M7** — RETIRED / SUPERSEDED; not part of final Alpha 2
- **M8** — PASS / CLOSED; final assembled-state acceptance and freeze

Canonical records:

- `MILESTONE6_VALIDATION.md`
- `MILESTONE7_VALIDATION.md` — retirement record only
- `ALPHA2_FINAL_VALIDATION.md`

## M7 retirement decision

The temporary free-text CUSTOM behaviour overlay is not part of final Alpha 2.

The active launcher removes any previously applied M7 hooks before restoring the proven M6 runtime path. The active Control Surface does not render M7 controls and does not reserve port 8766.

Historical M7 source/commits remain in Git only as experimental evidence. Do not silently re-enable them.

Custom personality/profile behaviour is parked with future **LOCAL** inference work, where it can be designed as a local-model/profile capability instead of an instruction layered over normal Luna use.

## Frozen transport invariants

Do not retune this branch:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime ASR;
- Windows Silero endpointing with 700 ms sustained-silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot authority over microphone stop/final flush/playback lifecycle;
- versioned Project-owned `type:"kadence"` messages;
- no raw model-generated servo coordinates;
- no secrets or personal memory committed to Git.

## Future direction

The intended later cognition selector remains exactly:

- `LOCAL`
- `LUNA`

No AUTO mode and no silent fallback.

Alpha 3 and Beta work must occur on new branches created from the frozen Alpha 2 closure state. Alpha 2 itself is historical validated state and is not a development branch anymore.

## Branch closure rule

Do not commit new features, utility expansions, local-LLM work, UI experiments or transport changes to `kadence/2.0-alpha-2`.

If a critical historical correction is ever unavoidable, explicitly reopen the branch first and record why. Otherwise preserve it untouched as the Alpha 2 rollback/provenance checkpoint.
