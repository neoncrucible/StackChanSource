Kadence Desktop — install and update

Current update: 0.4.9 — working description parsing and bounded voice recovery.
Firmware remains 0.21.6; no flash. The accepted 0.4.3 voice transport and output
pipeline are retained. This update includes the 0.4.6 UnitV2 setup permission repair.
An already working paired UnitV2 service does not need reinstalling.

Vision → Camera now starts with LOOK & DESCRIBE: one fresh image, with the actual
view and description side by side. The outdated Gemini response parser is fixed.
Errors distinguish credentials, quota, timeout and missing/invalid descriptions.
Voice failures release the old turn, recover a stalled robot connection with a
cooldown and wait for your next touch. No failed question is automatically replayed.
Ambient presence no longer claims to be preparing audio. Overview shows the
active audio endpoint, cancellation and the last voice/recovery result.
Read PRODUCTION-HARDENING.txt for the evidence, limits and short acceptance check.

Vision has Camera, Perception, Profiles, Activity and Face check tabs. Profiles reads your
existing SQLite database, shows saved sample counts/dates and offers rename,
replacement, delete, recognition tests and a database backup button. Enrollment
shows accepted samples and an explicit Saved or failure message beside the controls.
The Perception tab shows whether automatic looks are enabled, why they are blocked,
what the last look found and whether a greeting was delivered.

Face check shows the actual image/source and distinguishes no face, small/blurred
faces and failed identity matching. Lighting is no longer blamed without evidence.
In Profiles, optionally check Keep 3 local review photos before Enroll or Replace
Samples. Select a saved profile to review its photos. Existing embeddings cannot
recreate old pictures; use replacement to add new ones. Photos stay on this PC.

The server now detects robot reboots even when USB remains connected, cancels the
interrupted voice turn and reconnects. Additional stage deadlines cover lost ACKs.
The captured firmware 0.21.6 I2C interrupt crash itself remains unresolved; this
host-only package does not claim to prevent that reboot.

Say "What can you see?", "Camera status", "Use the extra camera", "Enable automatic
perception", "Enable greetings" or "Turn privacy on". These phrases are direct
commands. Image descriptions require the Gemini key, including with Ollama reasoning.
Local recognition needs no cloud image request. Enabling greetings alone does not
enable automatic perception. Read CAMERA-PERCEPTION.txt for the short test sequence.

1. Quit Kadence completely, including its tray icon. Close any source host too.
2. Extract the entire desktop ZIP to a new folder. Do not run inside the ZIP.
3. Double-click Install-Kadence.cmd. No administrator account is needed.
4. Use the Kadence shortcut on your desktop. Click START SERVER in the app.

Future updates: extract the new package and run its Install-Kadence.cmd.
It verifies files, installs a separate version and updates the same shortcut.
No terminal commands, Python installation or firmware flashing are required.
This is a complete application update, not a binary delta or an automatic updater.
Keep the _internal folder with Kadence.exe; the executable is not standalone.

Applications: %LOCALAPPDATA%\KadenceApp\versions
Existing data and settings: %LOCALAPPDATA%\Kadence
Windows Credential Manager remains the credential store. Application updates
do not remove settings, reminders, projects, media or database backups.
The installer retains previous executables. Database rollback across schema
versions still requires the documented database backup procedure.

Ollama: choose Ollama (this PC), then qwen3.5:4b in the model dropdown.
REFRESH reads installed model names from the local Ollama service.
Finding a model does not prove it can generate a Kadence reply. With the server
stopped, TEST REPLY uses the selected model, the voice planner prompt and the
same 22-second deadline. It validates a generated reply without microphone,
speech, camera use or tool execution. Then START SERVER and try a voice turn.
The default is offered even when Ollama is unavailable; it does not download it.
Model/provider/output selections save automatically, or use SAVE SETTINGS.
Restart the server after changes. Credentials follow Remember when starting.

This package uses the already tested firmware 0.21.6. No firmware is included.
Alignment fix in host 0.3.8 was physically accepted on 2026-09-22, including
normal Ollama replies after correcting the model name.

Desktop 0.3.9 physical sign-off — 2026-09-22
Accepted build: ec766bf0c93bf5c1958e62f657bf0296cf30bd30
The owner confirmed all requested checks passed: launch using the desktop
shortcut, quit and reopen, saved Ollama / qwen3.5:4b selection, normal spoken
answers, and unchanged head/camera alignment after answering.
The initial START SERVER issue was resolved by the owner; its cause was not
reported. No further code change was needed for this acceptance.

Windows CI for this build passed 30 tests plus 8 subtests, the runtime gate,
and the packaged executable's worker, storage, local speech and shutdown
checks. Package update/reinstall and corrupt-package rejection were exercised
in CI. An update from this installed version to a future release has not yet
been physically tested. The previously accepted onboard camera two-click
quirk remains unchanged. Autonomous perception functionality is not signed
off by these desktop checks.


Desktop 0.4.0 perception candidate — 2026-09-22
Host 0.4.0 adds saved camera policy/privacy controls, single-owner camera
acquisition and bounded local face perception. Firmware remains 0.21.6; no
firmware flash is required. The accepted 0.3.9 desktop remains the rollback.

During Windows packaging, delayed first import of NumPy/OpenCV in the frozen
worker could deadlock after the control-reader thread had started. The frozen
worker now preloads those native modules before creating any worker thread.
The packaged executable gate, perception/voice regressions, runtime ownership
gate and artifact upload all passed after this loader-order change with the
normal dependency set. Physical camera/perception acceptance is still pending;
follow CAMERA-PERCEPTION.txt after installing the 0.4.0 candidate.


Desktop 0.4.0 physical sign-off — 2026-09-25
Accepted build: 3963b1c7d45fd2e8b4db9887e9418bdecb46ada9.
The owner confirmed camera switching, then reported all agreed Gate 1 checks
passed after resolving local Ollama availability. This supersedes the pending
acceptance status above. UnitV2 physical standby remains unverified.

Desktop 0.4.1 observation candidate — 2026-09-25
Adds upstream sensor salience proposals, occupancy-session continuity, desktop
observation diagnostics and bounded export. No reflex actions are enabled.
Automatic perception is paused pending Gate 2 acceptance. Schema v4 and firmware
0.21.6 are retained. The physically accepted 0.4.0 package is the rollback.

Desktop 0.4.2 Ollama correction — 2026-09-25
The owner reported the generic thinking-service failure in 0.4.1 even though
REFRESH found the selected qwen3.5:4b model. The screenshot proves tag discovery;
it does not identify the failing generation step. Source review found that
the planner required JSON but the Ollama request did not constrain its output,
and all request/parse exceptions were discarded as the same connection message.

Ollama planner requests now use a JSON schema for either a spoken reply or one
tool proposal. Tool validation and spoken confirmation still govern execution.
Direct text-stream callers remain text streams. Interrupted, empty, oversized,
token-limited and malformed replies fail without executing partial plans.

Voice failures now produce safe Diagnostics codes for connection, timeout,
missing model, rejected request, model error, stream failure or reply format;
an HTTP status is retained when present. Provider bodies, hidden thinking,
conversation text and credentials are not exported. The robot speaks a brief
cause-specific recovery message; it can still handle local notes/list/clock.

The 22-second planner, 52-second host and 55-second firmware budgets are retained.
Slow model loading or inference can still time out; TEST REPLY exercises the
same request path and deadline so discovery cannot hide that failure.
This build needs a physical Ollama reply check. Gate 2 hardware acceptance
remains pending; automatic perception/reflex actions remain paused.

Ollama API references:
https://docs.ollama.com/api/chat
https://docs.ollama.com/capabilities/structured-outputs

Desktop 0.4.3 voice latency candidate — 2026-09-26
Windows speaker / Bluetooth now starts playing arriving speech instead of
waiting for the entire spoken answer. First-sentence preparation overlaps
reasoning, but playback waits for a validated complete reply. Ollama preloads
the selected model at server start and retains it for 30 minutes between uses.
Ordinary answers are shorter without changing Kadence's persona or saved model.

Diagnostics shows FIRST AUDIO and numeric Ollama stage timings. Read
VOICE-LATENCY.txt for the measured bottleneck, output-mode scope, comparison
steps and optional qwen3.5:2b model. Firmware remains 0.21.6; no flash is needed.
The 2–3-second target and audible quality require physical acceptance.

Desktop 0.4.3 responsiveness sign-off — 2026-09-26
Accepted build: 5798b75415122c8e7823019e5199a146651a926e.
The owner confirmed that the longstanding response-delay issue was solved and
was happy with the result. Kadence-diagnostics(10).json confirms this build and
three completed turns returning to idle, with no runtime_issue or fatal events.
First Windows audio was measured at 6.816, 3.204 and 5.081 seconds after recording
reception. The improved experience is accepted; a consistent 2–3-second maximum
remains an unmet performance target. This supersedes the pending responsiveness
acceptance above without claiming separate cancellation, Bluetooth acoustic or
camera/perception sign-off. Keep this executable as the accepted voice baseline.
