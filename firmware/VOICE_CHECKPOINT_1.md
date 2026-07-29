# Voice Checkpoint 1

Robot microphone and speaker remain the only physical voice input and output. Wake word: `Kadence`, pronounced like `Cadence`.

Current staged test: prove the green listening cue, chirp playback, pulsing listening frames and clean return to idle before connecting the live speech transport.

## Hardware validation note — 29 July 2026

Commit `15102a1a5a3e7155a66056f0155227d8ac5f94fe` physically passed the timing, chirp synchronisation, state exit and stationary safety checks. The observed pulse alternated between the green frame and an idle-looking frame rather than the intended green/red pair. Treat this as an asset identity or mapping issue to correct later; it does not invalidate the proven timing or safety foundation.
