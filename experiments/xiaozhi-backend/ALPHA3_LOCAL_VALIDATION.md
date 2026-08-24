# Project Kadence 2.0 — Alpha 3 LOCAL Standalone Validation

Validated physically on Windows: 24 Aug 2026

## Scope

This checkpoint validates only the first Alpha 3 server-only LOCAL inference slice.

No Xiaozhi server, robot transport, robot firmware, Control Surface selector, Home Assistant, timers, persistent memory, AUTO routing, M7 behaviour controls, or JSON profile system was exercised by this gate.

## Code under test

Branch: `kadence/2.0-alpha-3`

Initial LOCAL bring-up checkpoint:

`9831f9762804419c85e92558fbca91cd569c4705`

Shutdown lifecycle fix checkpoint:

`bbf23450adddeb3f9f50220c5d4565f12a90db11`

Frozen Alpha 2 remains unchanged.

## Machine / runtime evidence

- Ollama for Windows: 0.32.15
- Candidate model: `qwen3.5:4b`
- Model size reported by Ollama: 3.3 GB
- GPU: NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB VRAM
- Ollama placement: 100% GPU
- Context: 8192
- Canonical persona SHA-256: `7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1`
- Project-owned model store: `.runtime/local/ollama/models`
- LOCAL listener: `127.0.0.1:11434`

## Physical test sequence

The operator ran `test_local_windows.ps1` after installing Ollama and ensuring the normal Ollama app/server was not occupying TCP 11434.

Observed sequence:

1. Project-owned Ollama started.
2. `qwen3.5:4b` was already present in the Project-owned model store and preloaded.
3. Ollama reported the model as 100% GPU.
4. Factual prompt completed correctly.
5. Personality prompt completed and addressed the operator as Boss.
6. LOCAL stopped and TCP 11434 was released.
7. LOCAL restarted successfully.
8. Restart prompt completed correctly.
9. LOCAL stopped again and TCP 11434 was released.
10. The harness printed its completed-gates line and final metrics table.

## Responses and measured performance

### Factual prompt

Prompt: `What is the capital of Norway? Answer in one sentence.`

Response: `The capital of Norway is Oslo.`

- Wall: 509.3 ms
- Load: 2.1 ms
- Prompt tokens: 644
- Eval tokens: 8
- Generation: 83.63 tok/s

### Personality prompt

Prompt: `I have just spent twenty minutes debugging a problem that turned out to be a loose USB cable. What do you say?`

Observed response included dry teasing, practical follow-up, and the canonical `Boss` address.

- Wall: 1318.4 ms
- Load: 1.6 ms
- Prompt tokens: 656
- Eval tokens: 82
- Generation: 78.79 tok/s

### Restart prompt

Prompt: `In one sentence, what does a DNS A record do?`

Response correctly stated that an A record maps a domain name to an IPv4 address.

- Wall: 705.5 ms
- Load: 2.0 ms
- Prompt tokens: 644
- Eval tokens: 24
- Generation: 79.63 tok/s

## Shutdown note

The second stop emitted a benign `taskkill` exit-code 255 warning after the recorded parent PID had already exited. The shutdown script then explicitly verified TCP 11434 release and completed cleanly. A subsequent operator inspection showed:

- no remaining Ollama processes;
- no listener on TCP 11434;
- GPU memory returned to ordinary desktop usage.

This is therefore not treated as a process or port leak.

## Result

**PHYSICALLY ACCEPTED for the Alpha 3 standalone LOCAL slice.**

Accepted gates:

- exact Alpha 3 provenance;
- Project-owned LOCAL runtime start;
- factual answer;
- canonical-personality answer;
- clean ownership-aware stop with no listener leak;
- restart;
- post-restart answer;
- final stop with no listener leak;
- full GPU execution on the target RTX 3060.

`qwen3.5:4b` is accepted as the current LOCAL baseline candidate because latency and throughput are comfortably within the useful range on the target machine. This does not freeze the model permanently; later comparison remains allowed if a materially better quality/latency tradeoff appears.

## Next gate

Proceed to the existing Control Surface only after this checkpoint.

Required next behaviour:

- explicit LOCAL / LUNA selection visible before startup;
- no AUTO mode;
- Start launches only the selected engine path;
- Stop cleans only the active path;
- LOCAL failure must surface with no LUNA fallback;
- LUNA failure must surface with no LOCAL fallback;
- existing accepted M6 + EYE surface remains the base;
- retired M7 DEFAULT/CUSTOM behaviour controls must not return;
- robot/firmware/transport remain closed during this Control Surface slice.
