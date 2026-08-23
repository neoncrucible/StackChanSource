# Kadence 2.0 Alpha 2 — Final Validation and Freeze

Status: **VALIDATED / FROZEN**

Date closed: **23 Aug 2026**  
Branch: `kadence/2.0-alpha-2`

## Final physically accepted runtime anchor

`348e7c0fc05a027ba9affc7677534e488bd338c9`

This is the runtime/source state physically exercised immediately before Alpha 2 close-out. Documentation commits made after this checkpoint are closure bookkeeping only and must not be described as separately physically tested.

Backend CI at the final physical runtime anchor:

- `kadence-alpha/backend-tests`: **success**

The firmware status on that later backend/docs commit is not the firmware acceptance authority. The physically accepted firmware remains the dedicated M6 checkpoint below.

## Physically accepted firmware anchor

`995a2556f42e030660d6ed651b782987ac4a3d8e`

- `kadence-alpha/firmware-build`: **success**
- physically flashed and accepted on the robot;
- static trusted pixel weather icons physically verified.

## Proven provenance

- Frozen Alpha 1 head: `2d9ca4d515cee8f32f7d4fa0ecb7a80d17093ee1`
- Physically validated Alpha 1 firmware checkpoint: `b51bd762eb315b7bc330db0a5f9ecc1daa2183da`
- Pinned Xiaozhi upstream: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- Independent rollback line: `beta/project-kadence`
- M6 backend validation checkpoint: `6029c08cdcfbea6861daa4fb7b3cc7290a345569`

## Final Alpha 2 feature set

Alpha 2 closes on the proven M6 architecture plus the later Control Surface EYE geometry repair:

- canonical Project-owned Kadence identity;
- GPT-5.6 Luna only, `reasoning_effort: none`;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- Sonia Edge TTS;
- M4 bounded process-lifetime conversation continuity;
- M5 Project-owned safe allow-listed tool boundary;
- M6 read-only utilities:
  - `kadence_datetime`
  - `kadence_weather`
  - `kadence_web_lookup`
- trusted weather-display enum only: `clear | cloud | rain | snow`;
- static pixel weather icons on the robot;
- M6-era Control Surface with the EYE scaled to 90% and recentered to fit the left panel.

No persistent personal memory, arbitrary OS execution, unrestricted MCP/IoT access, smart-home writes, model-driven motion or provider fallback is active.

## M7 retirement

The experimental DEFAULT/CUSTOM free-text behaviour overlay is **not part of Alpha 2**.

It was retired after later physical evidence showed inconsistent end-to-end behaviour application and a follow-on Control Surface regression. The user chose to remove it rather than continue carrying prompt-overlay complexity in normal Luna use.

Final Alpha 2 startup therefore:

- removes any prior ignored-runtime M7 hooks through `remove_m7_behavior_windows.ps1`;
- does not start the loopback behaviour-control endpoint;
- does not reserve port 8766;
- does not render the SESSION BEHAVIOUR / CUSTOM UI;
- restores the original proven M6 tool applier and runtime path.

Historical M7 source and commits remain in Git as experimental history only. They are not an active capability and must not be silently re-enabled.

Custom personality/profile work is parked with future LOCAL inference work.

## Final physical close-out evidence

The final physical run at `348e7c0...` demonstrated:

- Control Surface opened on the M6-era UI with no M7 behaviour controls;
- startup explicitly removed all previously installed M7 runtime components;
- canonical persona loaded with SHA-256 `7871c845...`;
- Luna loaded as `gpt-5.6-luna` with reasoning disabled;
- M5 safe tool boundary and M6 utility adapter installed cleanly;
- pinned Xiaozhi upstream `e1876...` verified;
- robot connected over the frozen Xiaozhi v1 WebSocket path;
- robot audio negotiation remained 16 kHz / 60 ms Opus;
- OpenAI Realtime ASR reported ready with the accepted 700 ms endpoint hold;
- advertised tool allow-list was exactly `kadence_datetime`, `kadence_weather`, `kadence_web_lookup`;
- a physical weather request for East Cowes invoked the accepted weather tool;
- trusted UI result `weather_icon=clear` was emitted;
- Kadence completed a coherent spoken East Cowes weather reply through TTS.

This final smoke confirms that retiring M7 returned the assembled system to the accepted M6 operating architecture without reopening the frozen transport.

## Accepted known limitations / observations

- Broad or ambiguous geographic names can resolve unexpectedly; Kadence may identify that ambiguity and request a more specific place. Specific city/place weather queries are the intended use. This is accepted for Alpha 2 and is not a blocker.
- Previously observed chat-title `NoneType` / missing-close-frame warnings occurred during client disconnect/reconnect teardown and were non-blocking. Do not reopen transport unless they become reproducible and user-visible.
- A previous long answer was followed by a robot/client disconnect. The answer itself completed through TTS and the event was not shown to be caused by the LLM/transport settings. No transport retuning is justified by that isolated observation.

## Frozen transport invariants

Do not alter this Alpha 2 branch to retune:

- Xiaozhi v1 bidirectional WebSocket transport;
- 16 kHz / 60 ms Opus robot uplink;
- OpenAI Realtime ASR;
- Windows Silero preferred endpointing with 700 ms sustained-silence hold;
- ESP32 AFE fallback;
- 180 ms final Opus flush;
- 10 s hard capture cap;
- robot-owned microphone stop/final flush/playback lifecycle;
- versioned Project-owned `type:"kadence"` messages.

## Milestone disposition

- M0 — PASS / CLOSED
- M1 — PASS / CLOSED
- M2 — USER ACCEPTED / CLOSED
- M3 — PASS / CLOSED / HISTORICAL
- M4 — PASS / CLOSED
- M5 — PASS / CLOSED
- M6 — PASS / CLOSED
- M7 — RETIRED / SUPERSEDED; not part of final Alpha 2
- M8 — PASS / CLOSED as final assembled-state acceptance and freeze

## Freeze rule

`kadence/2.0-alpha-2` is now historical validated state.

Do not add Alpha 3 features, Beta utilities or new architecture to this branch. Any future changes require a new branch from the frozen Alpha 2 closure state, preserving this branch as rollback and provenance evidence.
