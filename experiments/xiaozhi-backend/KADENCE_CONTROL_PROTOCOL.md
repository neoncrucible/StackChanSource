# Kadence 2.0 Alpha 1 — Control Message Contract

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

- `type` must be exactly `kadence`.
- `version` must be `1` for this Alpha contract.
- unknown versions or events are ignored by firmware;
- control messages do not directly execute arbitrary model output;
- MCP remains ignored during Alpha 1.

## `endpoint`

The first defined control event is the server-side speech endpoint request:

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

## Compatibility

Firmware from before this contract ignores the unknown `kadence` message and continues using its local AFE endpoint. This makes server upgrades fail-safe instead of turning a control event into an apparent transport error.
