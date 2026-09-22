Kadence Desktop — install and update

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
