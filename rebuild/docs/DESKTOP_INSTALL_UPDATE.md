# Current candidate: 0.6.1 — grounded camera and companion repairs

Close Kadence completely, extract the entire new ZIP, run **Install-Kadence.cmd**
and keep Kadence closed for the robot update below. Existing settings, pairing
and faces are reused; no UnitV2 reinstall or face retraining is needed.

**To remove the fixed recording window:** run **Update-Robot.cmd** from the
extracted folder, select the CoreS3 / StackChan USB port and click **Update robot**.
Connect only the robot, with any StickS3 unplugged. The updater verifies the
matching 0.21.7 images, backs up robot NVS settings, writes only the allowed
firmware regions and verifies that NVS was preserved. It uses the bundled
flasher; no ESP-IDF installation or terminal commands are needed. Keep USB
connected until completion. Restart the robot, open the desktop shortcut and
click **Connect**.

0.21.7 ends capture after 720 ms of classified silence following detected speech.
Brief pauses stay within the utterance. Eight seconds is a ceiling, not a wait;
no-speech capture ends after three seconds. The old recording-window setting is
ignored for 0.21.7. Installing only the host leaves 0.21.6's fixed capture intact.

Camera questions now start the camera automatically. Say “What colour is this?”,
“Track that” or “Follow this pen”; there is no manual readiness/arming step for
visual tracking. Conversation keeps the target while head movement pauses.
Following now confirms a live target before claiming success and automatically
uses the saved Home, or establishes the original 0° yaw / 30° pitch baseline
through an acknowledged move. “Tell me if it gets moved” arms a real watch.
Home shows the actual image used for the answer. Awareness and greetings are
enabled once on upgrade, with privacy and individual face preferences preserved.
See **WHATS-NEW.txt** for the behaviour and limits and **TALK-NATURALLY.txt** for
camera, tracking, reminder and follow-up examples.

For the fastest audible response, **Settings → Voice & connection → Speaker**
offers PC / Bluetooth streaming. Existing saved speaker choices are preserved.
Robot and Both use the existing complete-buffer robot transport.

This is a candidate pending physical timing on the owner's robot. Keep the
accepted 0.4.13 installation and 0.21.6 firmware available. SQLite remains schema
5. Keep Stick remote off; its microphone work is parked. Robot 0.21.7 is a new
hardware acceptance candidate, not a claimed physical sign-off.

---

## Historical candidate: 0.5.0 — consolidated console (M1)

This is a host-only candidate, not a physically accepted release. CoreS3 remains
0.21.6, UnitV2 remains on its existing service (current source 1.3.0), and SQLite
remains schema 5. Preserve the accepted 0.4.13 package and its matching data
backup before installing. No robot flash, camera update or face retraining is
needed for this console change. Keep Stick remote OFF; its microphone work is
parked.

The console now has four pages:

- **Home:** live voice/camera/sensor state, next reminder, cancellation, Privacy
  and a single OFF / EVENT ONLY / AWARE selector. The selector enables or disables
  the existing automatic perception service. Changes wait for service confirmation;
  an unavailable camera or failed lifecycle test gives a reason instead of claiming
  awareness is running. Privacy stays available during voice and pending awareness
  changes. Saved preferences do not prove the camera producer has stopped.
- **Activity:** bounded live decisions and saved perception history, including
  suppression reasons. No routine sensor sample feed or automatic image gallery.
- **Tools:** Reminders, Workbench, Camera and explicitly armed Tracking.
- **Settings:** camera/greeting preferences, audio/display controls and Profiles.
  Expand **Engineering** for Connection & services (including API keys and Ollama),
  UnitV2 start/stop, Perception checks, Face check, UnitV2 training, Motion, Factory
  Vision, Stick controls and Diagnostics. These are the existing service controls.

Tray reminder notifications open Tools → Reminders. Quiet hours, do-not-disturb
and the remaining passive-coordination changes belong to M2; they are not part of
this candidate. The known device volume/top-swipe issue remains open.

Before installing, collect the read-only M0 report from the existing Windows
installation using `rebuild/tools/baseline_audit.py`; see `KADENCE_CURRENT.md` for
operator instructions and remaining evidence. The audit reports schema, field
metadata, row counts, snapshot health and package hashes without returning stored
notes, identities, images or credentials. It never performs an upgrade or backup.

1. Quit Kadence completely, including its tray icon. Keep the previous install.
2. Extract the complete verified candidate ZIP to a new folder.
3. Run Install-Kadence.cmd. It verifies the package and retains previous versions.
4. Open the Kadence desktop shortcut, check saved settings, then START SERVER.

Rollback: quit the candidate and launch the retained accepted executable from its
original version folder. This candidate introduces no database migration. If a
later release changes the schema, follow that release's database recovery steps.
A SQLite backup does not include native UnitV2 face features.

The source handover is authoritative: KADENCE_CURRENT.md on main. Instructions
below describe previous releases only; do not apply their firmware/setup steps to
this host-only update.

---

## Historical update: 0.4.14 — StickS3 Remote and shared Motion home

Install the complete desktop ZIP as usual. Robot firmware remains 0.21.6 and
UnitV2 service remains 1.2.0. No robot or camera flash is required. Read
STICKS3-REMOTE.txt for flashing only the StickS3, USB pairing, Remote ON/OFF,
unlimited-duration PTT and the shared Motion/Tracking Home controls.

Previous release instructions follow for historical reference.

Kadence Desktop — install and update

Current update: 0.4.13 — native object tracking and optional head following.

Face recognition/greetings in 0.4.12, audio in 0.4.11, scene descriptions,
start/stop and Privacy are physically accepted. This update adds a Tracking tab
and retains those baselines. Firmware stays at 0.21.6 and SQLite at schema 5.
No robot firmware flash, audio reconfiguration or new face training is required.

Run SET UP UNITV2 once to install camera service 1.2.0, power-cycle UnitV2, then
TEST START / STOP. Native face profiles, pairing and the original service backup
are preserved. Read OBJECT-TRACKING.txt for target selection and head setup.

Vision → Tracking → OPEN PREVIEW lets you draw a box around an object locally.
FIND & TRACK or “Kadence, follow this pen” uses the existing Gemini key to locate
one target, then the UnitV2 factory tracker follows it locally. Hold it still
while it is selected. Head following is OFF until explicitly armed in the tab;
UnitV2 must be attached to the moving head. Follow the slow direction check in
OBJECT-TRACKING.txt before normal use. Stop, Privacy and voice prevent new motor
steps; an already-issued bounded step finishes and releases torque first.

OpenClaw, other native vision modes, object movement alerts and physical idle
reflexes remain separate work. This build does not monitor theft. Tracking
occupies the camera until stopped; automatic face perception resumes eligibility
when it is released. Sessions expire after 15 minutes and are not auto-restored.

NATIVE-UNITV2-FACES.txt remains the face-training reference. Native files contain
features, not photographs. Existing PC review photos remain available. Earlier
schema 4→5 upgrade backup rules still apply; 0.4.12→0.4.13 adds no schema migration.

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
