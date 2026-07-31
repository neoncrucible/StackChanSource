# Project Kadence Beta

Project Kadence is now the product identity. The Alpha 1 firmware checkpoint remains preserved at `77c8dd6ba416799cb6f26320c1759ba9f1b60120`; this branch begins the independent Beta phase.

## Branch purpose

- preserve the signed Alpha 1 voice, motion, display, LED and torque behaviour;
- move all user-facing identity to Project Kadence;
- add the new Project Kadence Beta boot splash;
- keep model and server optimisation outside the signed firmware checkpoint until each change has its own test gate;
- remove legacy product branding from new user-facing assets, logs and documentation;
- retain third-party and hardware attribution only where legally or technically required.

## Beta splash

Run:

```powershell
cd "C:\AI Project\Droid-dev-fresh"
py firmware\tools\generate_project_kadence_beta_splash.py
```

Expected output:

`firmware/assets/project-kadence/beta_splash.png`

The generated image is exactly 320 x 240 pixels and contains only the Project Kadence identity. It is staged for integration into the next firmware update; creating this branch does not alter the physically signed Alpha 1 runtime.

## First Beta gates

1. Integrate and physically verify the new splash.
2. Correct the AFE feed/ringbuffer watchdog condition without altering wake, VAD or playback behaviour.
3. Keep voice-server latency work on the Windows service branch.
4. Add new capabilities only through approved intents and fixed robot presets.
5. Do not expose raw motion coordinates to model output.

## Source of truth

The signed Alpha 1 parent commit is the rollback point. The Beta branch must remain independently buildable and every firmware package must retain its manifest, internal SHA256SUMS and exact flash offsets.
