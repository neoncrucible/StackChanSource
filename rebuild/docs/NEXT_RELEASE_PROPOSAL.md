# Kadence next release — approved implementation scope

**Status: FIRST BUNDLE APPROVED by Boss on 7 September 2026; quiz removed.**

**Date:** 7 September 2026

**Baseline:** approved RC1 at `997654857c3dd6aa2f78c92501c2eda2bf6744fe`

Boss approved the first bundle, removed Quiz Night, and explicitly added natural
dated reminders: “remind me at…” and “tomorrow remind me I need to…”. Implement
the approved scope without requesting approval again. Continuous tracking and
enrolled-person profiles retain the later camera qualification/review boundary.
Home Assistant actions still need the owner's actual configured devices.

## Recommended release shape

Build the utility services and their Windows controls together. Define their
commands, status and stored data first, then connect both voice and UI to those
same services. Deliver one coherent desktop-and-device release after approval.

The first proposed bundle contains the Windows console, three practical
utilities, one game, both top LED strips, top-touch volume and deliberate camera
snapshots. Face tracking and enrolled-person recognition follow a separate camera
qualification step. Reserve their UI space now without making the first bundle
depend on continuous video performance.

The current notes, tasks, arithmetic, clock, weather and read-only home status
remain useful building blocks. They are already implemented and are not being
counted as newly added utilities.

## Windows application

Use a solid black surface with restrained phosphor-green text, terminal-style
panels, readable monospaced labels and clear buttons. Carry through the approved
avatar's identity. Keep long logs in a secondary view so routine operation fits
in a normal desktop window with Windows scaling and keyboard navigation.

| Area | Proposed controls and information |
|---|---|
| Server | Start, Stop, Restart; explicit starting, running, stopping and stopped states; uptime and robot connection. |
| Credentials | OpenAI, Gemini and Wi-Fi fields with individual show/hide controls; session-only use by default; optional “Remember on this Windows account” and “Forget saved credentials”. |
| Connection | COM selector, network/SSID and LAN adapter selection; distinguish a running server from a connected robot. |
| Activity | Listening/thinking/speaking/tool state, last completed turn, provider-stage timings and a bounded event log. Export only a sanitised diagnostic report. |
| Utilities | Timers, project notebook, checklists, calculator/conversions and games; show actual service results and pending confirmations. |
| Device | Volume/mute, LED brightness, camera-off/active/paused state and deliberate snapshot controls. |
| Vision | Latest requested image and description; later tracking and enrollment controls when supported. |

PySide6/Qt is the recommended desktop framework because it fits the existing
Python host and has an official Windows packaging route. Package the application
with its own tested runtime and dependencies so everyday startup does not depend
on the terminal's ESP-IDF environment. This is an engineering recommendation,
not an already-built executable. [Qt deployment documentation](https://doc.qt.io/qtforpython-6/deployment/index.html)

The UI supervises exactly one host process. The host retains the sole serial
connection and all utility authority. A private, bounded local control channel
carries typed status and graceful stop requests; UI controls must not open COM4
or infer success from arbitrary log text. Start is disabled during start/stop
transitions. Stop cancels active work, releases the device and waits for shutdown.
Tray operation can keep the host running; an explicit Quit stops it. Test closing
and reopening the window, duplicate launches and a stop during active playback.

Optional remembered credentials belong in Windows Credential Manager. They must
not enter command-line arguments, diagnostic exports or ordinary settings JSON.
Session-only use stays available. Microsoft documents the OS credential vault
for this purpose. [Windows credential handling](https://learn.microsoft.com/en-us/windows/win32/secbp/handling-passwords)

## Three practical utilities

| Utility | What it adds | Windows UI | Feasibility and dependencies |
|---|---|---|---|
| Focus and reminders | Named countdowns, scheduled reminders, a focus/break cycle, snooze and cancel. “Remind me to check the print in twenty minutes.” | Countdown cards, next due time, reminder list and snooze/cancel. | High confidence on the host. Persist due times and deliver visual alerts without a speech provider. Requires a new unsolicited alert path to the robot. |
| Lab workbench | Project-scoped notes, resumable step-by-step checklists, unit conversions and deterministic electronics calculations such as Ohm's law and resistor values. “Resume the sensor checklist.” | Project selector, current checklist step, searchable records and calculation input/results. | High confidence; extends the existing local store and tool boundary. Voice still uses the speech providers; direct UI operations can be local. |
| Visual desk assistant | A requested camera snapshot, identification of common desk objects, readable large labels and QR codes, with a saved project observation only when asked. “What am I holding?” | Capture/retake, image preview, result, and explicit save-to-project. | Viable with qualification. Use host decoding/vision and an optional configured multimodal provider. Small print, tiny components and exact part numbers may exceed this camera's useful detail. |

Timers need an explicit lifecycle: stored deadlines survive a restart, while
notifications run only when the host is running and Windows is awake. On restart
or wake, show missed reminders once rather than replaying a backlog. Robot alerts
must wait for or negotiate the existing voice/audio lane; they must not interrupt
playback by starting a second speaker owner. Local Windows alerts should work
even if the robot is disconnected or a speech service is unavailable.

For the workbench, show units and inputs with numerical results. Keep arithmetic
and conversions deterministic. Reuse existing notes/tasks through a versioned
store migration and preserve the owner's current records. Saved project images
are a new, explicit storage choice, separate from transient camera frames.

### Optional fourth utility: lab/home controls

If the owner uses Home Assistant, add allowlisted desk lighting and selected
scenes, alongside the existing sensor/status reads. This would provide a useful
control panel as well as voice operation. It needs the owner's actual entity list
and chosen actions before implementation; a Home Assistant installation has not
been established in this session. Require explicit action confirmation where
appropriate and report the resulting entity state rather than assuming success.
Use the official service-call API for device actions. [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)

This is optional and is not one of the three baseline utilities. Existing NFC
and infrared hardware are promising later inputs, but adding those drivers is
outside this first proposed bundle.

## LED memory game

| Game | Interaction | UI / device requirements |
|---|---|---|
| LED memory game | Repeat a growing sequence across three clearly marked top-touch zones, with the two strips showing the pattern and progress. | Explicit game mode, score/best score, sound option and front-screen cancel. Top-zone game input temporarily replaces volume gestures only while this visible mode is active. |

The game should be a bounded session that can be stopped immediately. Light feedback
and avatar responses should use the normal presentation state system. The game
must not create another motor, audio, touchscreen or top-touch polling loop.

## Official top-strip control

M5Stack specifies twelve WS2812C LEDs in two rows. Its RGB example maps indices
0–5 to the left row and 6–11 to the right, sets per-pixel RGB values and refreshes
the result. [StackChan specifications](https://docs.m5stack.com/en/StackChan),
[official RGB example](https://docs.m5stack.com/en/arduino/stackchan/rgb)

The BSP routes LED control through the **PY32 I/O expander**: its pin 13 is
configured as the LED output, the count is set to twelve, and colour writes are
followed by a refresh. Pin 13 here is the expander's pin, not ESP32 GPIO13; the
rebuild already uses ESP32 GPIO13 for audio. Use the expander's protocol on the
existing I2C bus. Do not install a second direct-GPIO LED driver or invoke the
whole Arduino board initialiser. [Official BSP implementation](https://github.com/m5stack/StackChan-BSP/blob/main/src/M5StackChan.cpp)

The repository's `firmware/main/hal/hal_io_expander.cpp` and
`firmware/main/hal/drivers/PY32IOExpander_Class/` corroborate this route and are
reference material, not code to merge wholesale into the rebuild. Preserve the
expander bits that control servo power and the separate CoreS3 expander state.

Proposed presentation: a restrained green travelling pattern across both strips
while thinking, a distinct listening indication, audio-responsive speaking and
a brief volume bar after adjustment. Expose brightness and quiet/dim settings in
Windows. Compute frames locally from the existing state and audio meter; send
bounded colour updates through the existing I2C ownership. Batch writes where
the controller supports them and skip stale frames under load. A camera-active
indicator has priority over decorative effects.

## Top-touch volume

The top panel is separate from the front touchscreen. M5Stack's example exposes
click, forward-swipe and backward-swipe events from `TouchSensor`; the underlying
sensor has three zones. [Official touch example](https://docs.m5stack.com/en/arduino/stackchan/touchsensor)

Recommend a swipe toward the front to increase volume in 5-point steps and a
swipe toward the rear to decrease it. A deliberate long hold toggles mute, with
the previous nonzero volume remembered. Confirm direction on the physical device
before finalising labels. Keep the front touchscreen's talk/cancel action.

Apply gain through the existing audio owner, with bounded updates during playback
and a configurable maximum. Reflect the acknowledged level in Windows and briefly
on the strips/display. Persist a settled setting rather than writing flash on
every touch sample. The GUI volume control uses the same command and state;
neither side should display an unacknowledged value as applied.

## Camera and familiar people

The GC0308 is a 640×480 camera. M5Stack demonstrates a 320×240 RGB565 capture
using PSRAM and camera control on SDA12/SCL11. Its standalone example releases
the existing M5 I2C object before camera initialisation. Kadence must preserve its
existing bus and hardware owners; use the documented wiring and a compatible
camera control integration without copying that standalone initialisation.
[Official camera example](https://docs.m5stack.com/en/arduino/stackchan/camera)

The RGB/YUV capture path, display buffers, Wi-Fi and staged audio all compete for
resources. Espressif specifically warns about PSRAM pressure with RGB/YUV and
Wi-Fi. Budget capture buffers, conversion and network traffic before enabling
continuous capture. Do not assume the sensor emits JPEG just because a driver
example for another sensor does. [Espressif camera driver](https://github.com/espressif/esp32-camera)

| Step | Proposed behaviour | Acceptance requirement |
|---|---|---|
| Snapshot foundation | One bounded requested image, live preview of that image, cancel and release. Camera initially off. | Repeated capture and cancellation without harming touch, avatar, voice playback or available memory. No retained image unless explicitly saved. |
| Object recognition | Identify common visible objects, decode usable QR codes and describe readable labels. Distinguish local decoding from a cloud-assisted description. | A real set of lab objects under normal lighting; express uncertainty. QR contents are data, never automatically executed or opened. |
| Face tracking | Host face detection drives the avatar's gaze first, then small bounded head corrections through the existing body executor. | Measure actual frame latency and motion stability. Use deadband, rate limits, stale-frame expiry and stop on loss of target. Voice/touch takes priority and torque-release rules remain intact. |
| Enrolled-person profiles | The owner deliberately enrolls a few consenting people, attaches names/preferences, and can delete them. Unknown faces remain unknown. | Local matching with thresholds and repeated agreement, plus tests of lookalikes and varied lighting. Identity guesses do not authorise actions or automatically disclose private notes. |

For tracking, start with low-resolution frames at a measured low rate; 2–5 fps
is an initial experiment target, not a promised result. Pause the camera stream
through microphone capture and staged playback, and make that pause explicit in
the UI. Frame traffic belongs on a bounded authenticated LAN media path, while
camera commands remain on the existing versioned serial control boundary.

Run face detection and enrolled-face matching on the Windows host. OpenCV's
YuNet/SFace path provides a practical reference for these distinct tasks; its
recognition model is much larger than the robot's RAM budget. Model benchmarks
do not establish accuracy on the actual StackChan camera. [OpenCV face detection and recognition](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)

Interpret “persona recognition” as recognising an enrolled person and selecting
their chosen greeting/preferences while preserving Kadence's identity. Do not
infer personality, emotions or sensitive attributes from a face. Store enrollment
templates locally with an explicit delete control; show when the camera is active
and when a requested snapshot will use a cloud provider. No continuous cloud
video is needed for tracking or familiar-face matching.

## Delivery and approval boundary

Within the approved scope, implement shared utility/status interfaces and desktop
supervision first, then LED/top-touch integration and the camera snapshot path.
Test the combined workload and deliver a commit-named desktop/firmware pair with
its updated operator manual. Preserve the approved RC1 artifact for rollback.

The owner approved the first bundle's scope and interaction choices:
Windows console, Focus and Reminders, Lab Workbench, Visual Desk Assistant,
LED Memory, thinking/status strips and swipe-volume controls. Quiz Night was
explicitly excluded by the owner.
Recommend separate approval for continuous tracking/enrolled-person recognition
after the camera measurements, and for Home Assistant actions once the desired
devices are known. Approval is recorded above; proceed with the first bundle. The later qualification
and account-specific boundaries do not block the approved work.

## Dated reminders — explicit owner addition

Use the host clock and configured IANA timezone (Europe/London by default) as
authoritative current-date context, refreshed for every reasoning turn. Resolve
“tomorrow” by local calendar date, store the actual UTC instant with timezone,
and read back the resolved date and time. Support “remind me at…”, “tomorrow
remind me I need to…”, named weekdays, explicit dates and relative countdowns.
Ask for missing times, AM/PM ambiguity, past times and daylight-saving gaps or
repeated hours; do not silently invent a default. Keep clarification attached to
the requested reminder across the next completed turn. Persist reminders and
provide list, snooze, cancel and dismiss controls shared by voice and Windows.
