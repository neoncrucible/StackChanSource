# Project Kadence 2.0 — Milestone 6 Validation

**Milestone:** M6 — first read-only utilities  
**Status:** **PASS / CLOSED**  
**Acceptance date:** 23 Aug 2026, Europe/London  
**Branch:** `kadence/2.0-alpha-2`

## Accepted user-visible scope

M6 adds exactly three read-only utilities through the already-closed M5 Kadence authority boundary:

- `kadence_datetime` — current date/time, optionally for a named place;
- `kadence_weather` — current / 7-day bounded point weather;
- `kadence_web_lookup` — bounded factual web lookup through OpenAI Responses web search.

M6 also adds one tightly bounded robot display side effect for weather:

- trusted backend handler maps provider weather codes to the fixed enum `clear | cloud | rain | snow`;
- backend emits a versioned Project-owned `type: "kadence"` `weather_icon` event;
- robot renders a static local pixel-art icon during the weather reply;
- no model-generated graphics, coordinates or animation are accepted;
- normal voice state wins on completion/cancel/error and the Idle EYE returns.

No smart-home writes, generic MCP/plugin access, arbitrary URLs, shell/process/filesystem execution, model-driven motion or transport retuning were added.

## Exact accepted checkpoints

### Backend / utility behaviour

Final M6 backend behaviour checkpoint before this validation record:

`6029c08cdcfbea6861daa4fb7b3cc7290a345569`

This includes the post-physical-test location-disambiguation repair.

### Firmware

Physically accepted pixel-weather firmware implementation:

`995a2556f42e030660d6ed651b782987ac4a3d8e`

Commit purpose: `Use pixel weather display overlay in M6 builds`.

The firmware build gate for this exact pixel-weather checkpoint passed under ESP-IDF 5.5.4 before flashing.

### Inherited provenance

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`.
- Physically validated Alpha 1 firmware rollback checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`.
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`.
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`.
- Active LLM from M6 onward: `gpt-5.6-luna`, `reasoning_effort: none`.
- Gemini remains retired after M5; there is no fallback provider.

## Utility architecture accepted

### Fixed network destinations

Project-owned utility code exposes no model-supplied URL surface. Remote destinations are constants:

- Open-Meteo geocoding;
- Open-Meteo forecast;
- OpenAI Responses API for factual web search.

Remote calls have bounded timeouts and response-size ceilings. Errors are converted into contained `KadenceUtilityError` failures.

### Weather display authority

The primary Luna model supplies only schema-validated weather arguments. The trusted handler alone derives `_kadence_ui.weather_icon`; the runtime adapter removes that private hint before reinjecting the factual result into Luna and emits only an allow-listed enum value to firmware.

Firmware WebSocket handling records only the accepted enum. LVGL is touched from the main loop rather than from the WebSocket callback. Unknown/malformed values are ignored.

### Pixel display

The final accepted display uses static hard-edged pixel blocks rather than the earlier smooth prototype:

- clear — square sun/rays;
- cloud — stacked grey pixel blocks;
- rain — cloud plus blue rectangular drops;
- snow — cloud plus block-built snowflakes.

There is no animation in Alpha 2.

## Deterministic validation

The M6 utility suite passed before physical acceptance and covers:

- remote timezone offset/date rollover;
- current and future weather selection;
- all four bounded weather icon mappings;
- unknown-location failure;
- web answer/source extraction and source deduplication;
- fixed web endpoint and no model-supplied URL execution;
- OpenAI web-search-only request surface;
- disabled response storage;
- fixed allow-listed utility network destinations;
- visible failure when the web credential is unavailable.

After physical testing exposed the `Florida -> Floridablanca, Colombia` geocoding edge case, deterministic coverage was extended so broad administrative regions do not silently become unrelated prefix matches. The final utility resolver inspects a bounded candidate set, prefers exact place-name matches and fails closed for administrative-region/country point-weather requests.

CI on final M6 backend checkpoint `6029c08...`:

- `kadence-alpha/backend-tests`: **success**;
- `kadence-alpha/firmware-build`: **success**.

## Physical acceptance evidence

### Runtime / authority

Physical startup confirmed:

- canonical identity v1 and expected persona hash;
- Luna `gpt-5.6-luna`, reasoning `none`;
- M6 mode `m6_readonly`;
- exact advertised allow-list: `kadence_datetime`, `kadence_weather`, `kadence_web_lookup`;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- frozen 700 ms server endpoint policy;
- pinned Alpha 1 transport stack remained in use.

### Date/time

An explicit spoken Tokyo datetime request was reported physically successful. The named-place path therefore passed physical use as well as deterministic timezone/date-rollover tests.

### Weather / future forecast

An explicit spoken future-weather request for Paris was reported physically successful.

London physical weather test produced:

- `KADENCE TOOL: accepted name=kadence_weather`;
- `KADENCE UI: weather_icon=cloud`;
- coherent spoken current/forecast weather;
- static chunky pixel cloud icon on the robot;
- icon persisted through the weather response;
- normal Idle EYE returned afterwards.

A second physical weather turn produced the rain icon, proving a different enum/display path.

### Factual web lookup

Physical M6 server testing accepted multiple web lookups, including current software/version information and public factual queries. Luna autonomously selected the web utility when appropriate. No provider fallback or generic executor was involved.

### Session continuity coexistence

M4 continuity remained intact across normal and utility turns. Follow-up references worked and reconnect hydration retained completed exchanges. No persistent memory was introduced.

## Physical defect found and repaired

### Original defect

The first broad query:

`What's the weather in Florida?`

was passed to Open-Meteo with a single geocoding result. Open-Meteo prefix matching selected `Floridablanca, Colombia`; the weather tool therefore returned internally consistent but geographically wrong data. Luna noticed the returned label and warned the user, but the trusted utility had already selected the wrong point.

This was treated as an M6 correctness defect rather than waived.

### Repair

Final backend checkpoint `6029c08...` narrows resolution behaviour:

- bounded multi-candidate geocoding instead of `count=1`;
- exact place-name matches preferred over prefix matches;
- administrative regions/countries rejected as too broad for a point forecast;
- weather tool description tells Luna to request a city/town rather than invent a representative point.

### Final physical retest

After pulling the repaired backend, the same spoken request:

`What's the weather in Florida?`

correctly produced a clarification asking for a city/town and did **not** execute a bogus Florida forecast.

A quiet spoken follow-up was ASR-transcribed as `Temple.` The follow-up still demonstrated the intended M4/M6 interaction:

- retained context associated the place with Florida;
- `kadence_weather` was accepted;
- trusted `weather_icon=clear` was emitted;
- a coherent point forecast was spoken.

The ASR transcription itself was not treated as an M6 utility defect because the user was intentionally speaking quietly and accepted the recognition result as non-blocking.

## Non-blocking teardown observation

During the final test the robot disconnected/reconnected after the completed response. Xiaozhi logged its existing chat-title `NoneType` warning and one `audio_play_priority_thread` missing-close-frame error. The server immediately accepted the reconnect, restored the M6 allow-list and hydrated two retained exchanges.

This is recorded as teardown/reconnect noise, not an M6 failure, because it was not user-visible as a functional loss, did not crash the backend, did not lose M4 continuity and did not reproduce as a utility-path failure. Do not reopen frozen transport for this observation unless future physical evidence makes it reproducible or user-visible.

## Gate result

M6 gate:

> Repeated physical tests mix ordinary conversation and read-only utility calls without fabricated results or infrastructure leakage; Alpha 2 acceptance is Luna-only.

**Result: PASS / CLOSED.**

The one physically discovered factual-resolution bug was repaired, covered deterministically and physically retested before closure.

## Frozen M6 scope going forward

Do not silently expand M6 to include:

- Tapo/Home Assistant/device control;
- timers/reminders;
- arbitrary web fetching;
- generic MCP/plugin execution;
- persistent memory;
- LOCAL inference;
- new expressions/animation;
- transport tuning.

Next milestone: **M7 — temporary session behaviour overlay from the Control Surface**.
