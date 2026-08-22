# Kadence 2.0 — Control Message Contract

Kadence continues to use Xiaozhi version-1 WebSocket messages for normal conversation state and Opus audio. Project-specific device controls use a separate JSON namespace so they are never disguised as Xiaozhi errors, STT, TTS or MCP messages.

## Envelope

Server-to-device control messages use:

```json
{
  "type": "kadence",
  "version": 1,
  "event": "<event-name>"
}
```

Rules:

- `type` must be exactly `kadence`;
- `version` must be `1` for this Alpha contract;
- unknown versions or events are ignored by firmware;
- each event defines its own tightly bounded payload;
- control messages do not directly execute arbitrary model output;
- generic MCP/model-driven device control remains outside the Alpha 2 contract.

## `endpoint`

The server-side speech endpoint request is:

```json
{
  "type": "kadence",
  "version": 1,
  "event": "endpoint",
  "source": "silero",
  "silence_ms": 704,
  "session_id": "..."
}
```

Semantics:

1. Windows Silero must first observe genuine user speech.
2. Silero must then remain continuously silent for the configured hold (`700 ms` in the frozen Alpha baseline).
3. The backend sends `endpoint` once for that turn.
4. The message **does not** stop recording or start LLM/TTS itself.
5. Firmware accepts the request only while its voice UI is in `Listening`.
6. Firmware closes its microphone capture gate, flushes final Opus for `180 ms`, then sends the ordinary Xiaozhi `listen/stop` message.
7. The ESP32 AFE endpoint and ten-second capture cap remain independent fallback paths.

This separation is intentional: the server may detect end-of-speech, but the robot remains authoritative for its own microphone and playback state.

## `weather_icon` — Alpha 2 M6

M6 adds one bounded utility-display event:

```json
{
  "type": "kadence",
  "version": 1,
  "event": "weather_icon",
  "condition": "rain"
}
```

Allowed `condition` values are exactly:

- `clear`
- `cloud`
- `rain`
- `snow`

Semantics:

1. The model cannot send this event directly.
2. The Project-owned weather handler maps Open-Meteo weather codes into the fixed four-value enum.
3. The Kadence tool adapter strips the private display hint from the factual tool result before that result is reinjected into Luna.
4. Firmware validates the event/version and condition again. Unknown or malformed values are ignored.
5. The network callback only records the enum; LVGL is updated from the normal firmware loop rather than from the WebSocket callback.
6. The static weather icon may replace the EYE while the weather reply is being generated/spoken.
7. When the voice turn returns to `Idle` (or enters `Error`), the overlay is hidden and the established EYE state resumes.
8. This event cannot move servos, change microphone authority, alter endpoint timing or invoke arbitrary graphics.

The weather display is therefore a bounded utility visualization, not a general model-controlled expression system.

## Compatibility

Firmware from before this contract ignores unknown `kadence` messages and continues normal voice operation. This makes server upgrades fail-safe instead of turning a new control event into an apparent transport error.
