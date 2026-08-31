# Architecture contract

This document records invariants rather than product presentation details.

1. Device owns physical I/O, local safety and immediate feedback.
2. Host owns cognition, memory, orchestration and integrations.
3. Device and host communicate only through a versioned protocol boundary.
4. STT, reasoning, TTS and tool bridges are replaceable providers.
5. Identity/presentation is independent of model provider.
6. Loss of any external integration must not prevent basic device operation.
7. Startup must expose deterministic health states and diagnostics.
8. Long-running operations must be cancellable and must not block presence updates.
