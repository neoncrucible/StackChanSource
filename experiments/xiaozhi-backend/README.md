# Kadence 2.0 Alpha 2 — Windows Runbook

Current branch: `kadence/2.0-alpha-2`

This directory hosts the Windows backend/runtime wrappers used by the physically validated Kadence 2.0 Alpha 2 stack. Historical Alpha 1/M3 details remain in their validation and close-out records; this file describes the **current** operating path.

## Current stack

- pinned Xiaozhi backend: `e1876f1ce19cad6e7bfd7c80e41dc56b2e858dd5`;
- 16 kHz / 60 ms Opus robot uplink over Xiaozhi v1 WebSocket;
- Windows Silero endpoint observation with frozen `700 ms` silence hold;
- OpenAI Realtime `gpt-realtime-whisper` ASR;
- GPT-5.6 Luna (`gpt-5.6-luna`, `reasoning_effort: none`);
- Edge TTS `en-GB-SoniaNeural`;
- M4 bounded volatile session continuity;
- M5 Project-owned safe tool boundary;
- no persistent personal memory, generic MCP execution, shell access or model-driven robot motion.

## Provider policy

From M6 onward Alpha 2 is **Luna only**.

Gemini was used during M3 benchmarking and M5 provider-abstraction validation, then retired from the active Kadence runtime/config/control path. It is not a fallback and no ongoing Gemini regression pass is required.

Future beta/live target is **LOCAL / LUNA** explicit selection only. There is no AUTO mode and no silent fallback: if the selected inference engine fails, the failure is surfaced.

The robot firmware remains provider-agnostic and does not contain a Gemini-specific inference path.

## Bootstrap

From this directory:

```powershell
.\bootstrap_windows.ps1
```

The bootstrap creates/refreshes the ignored Xiaozhi runtime and verifies the pinned upstream revision. Real API credentials are never committed.

The checked-in `kadence.config.example.yaml` contains one OpenAI placeholder. The ignored local runtime uses that credential for both Realtime ASR and Luna.

## Start with the Control Surface

Preferred operator path:

```powershell
.\start_control_surface.ps1
```

The packaged EXE may also be used when already built.

The Control Surface delegates backend startup to:

```powershell
.\start_alpha2_windows.ps1
```

Current startup sequence:

1. apply the Luna-only guarded runtime/M4 compatibility path;
2. inject the canonical Kadence persona;
3. force the accepted Luna profile;
4. apply the Project-owned safe tool boundary;
5. discover Conda;
6. delegate transport startup to `start_windows.ps1`;
7. verify pinned Xiaozhi, install/refresh Realtime ASR, locate FFmpeg and start the proven UDP discovery/WebSocket stack.

Until M6 replaces the inert M5 probe registry, startup still sets:

`KADENCE_TOOL_MODE=m5_probe`

This is temporary development state, not a production utility.

## Expected current markers

Useful startup lines include:

```text
Kadence canonical identity: v1 / sha256 7871c8453b3cf679c915c04220eef9bba14db535526d8e5bab666dbc66009aa1
Applying fixed Alpha 2 LLM profile: luna
Kadence LLM profile: openai-luna / model=gpt-5.6-luna / reasoning=none
KADENCE TOOLS: mode=m5_probe allowlist=['kadence_boundary_probe']
K2 ASR LIVE ready: model=gpt-realtime-whisper, 16k->24k PCM, endpoint=700ms
```

A normal Alpha 2 boot should no longer request a Gemini API key, select Gemini or apply Gemini provider compatibility/tool-roundtrip patches.

## Current active Project wrappers

- `patch_runtime_luna_windows.ps1` — frozen transport-adjacent Silero + M4 guarded runtime patching only;
- `apply_luna_profile_windows.ps1` — accepted Luna LLM profile and OpenAI provider compatibility;
- `apply_persona_windows.ps1` — canonical identity injection;
- `apply_kadence_tools_windows.ps1` — M5 safe tool plumbing;
- `start_windows.ps1` — proven discovery/ASR/transport launcher;
- `start_alpha2_windows.ps1` — Alpha 2 orchestration;
- `start_control_surface.ps1` — operator UI launcher.

Closed M3 benchmark executables and Gemini-specific runtime helpers were removed after M5. Their history remains in Git and their accepted conclusions remain in the milestone records.

## Physical smoke after runtime changes

A small smoke is enough unless the milestone-specific gate requires more:

1. start the Control Surface;
2. verify Luna is the active model;
3. verify robot connection and Realtime ASR readiness;
4. ask one ordinary factual question;
5. if tool plumbing changed, run the currently advertised safe utility/probe once;
6. confirm normal wake -> listen -> endpoint -> ASR -> think -> speak -> idle behaviour.

Do not flash firmware for server-only Alpha 2 changes.

## Stop / rollback conditions

Stop and investigate rather than retuning blindly if there is:

- repeated reboot/reconnect instability;
- microphone or AFE failure after a turn;
- persistent/reproducible audio corruption;
- cancellation failure;
- raw model-directed hardware motion;
- tool execution outside Kadence's explicit allow-list;
- credentials or personal conversation content appearing in tracked files.

Do not modify the frozen Alpha 1 branch to repair an Alpha 2 server regression. Use the validation records and recorded rollback SHAs to repair forward or revert on `kadence/2.0-alpha-2`.

## Next milestone

M6 adds the first real read-only utilities through the closed M5 boundary:

- date/time;
- weather;
- factual web lookup.

M6 acceptance is Luna-only. No Gemini duplicate test is required.
