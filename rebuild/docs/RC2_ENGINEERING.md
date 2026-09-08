# RC2 engineering and qualification

RC2 implements Boss's approved first bundle: Windows console, date-aware reminders
and focus, lab workbench, deliberate visual desk assistance, both top strips,
top-touch volume and LED Memory. Quiz Night is excluded. Continuous face tracking,
enrolled-person profiles and Home Assistant actions retain their separate review
boundaries. RC1 at `997654857c3dd6aa2f78c92501c2eda2bf6744fe` remains physically
approved; this candidate does not relabel that approval as proof of new hardware.

## Runtime ownership

`desktop_ui` uses Qt and supervises one `desktop_worker` through bounded private
NDJSON pipes. Credentials travel through that pipe, never argv or settings JSON.
The worker suppresses raw adapter logs and emits typed status only. Windows
Credential Manager is optional; only the Kadence-owned target is read/deleted.
The packaged executable retains standard streams for worker mode while hiding
its console window. A per-data-directory Qt lock prevents duplicate desktop starts.

The worker's `LocalServices` outlives robot Start/Stop. The same SQLite utility
store, reminder resolver, tool registry and scheduler serve voice and desktop.
Server lifecycle is serialised; startup failures close the old appliance before
it becomes available for restart. Quit sends a graceful stop, with bounded fallback.

`RuntimeBody` / `HostServer` still own serial and the command correlation registry.
Media commands use its command lock and late-response retirement. Device status
and volume settings can use the control plane during playback. There is one
existing firmware media worker for voice, alerts, snapshots and game notes.
The original staged PSRAM playback and internal DMA scratch remain in use.
Volume applies bounded Q15 attenuation with a short gain ramp; codec gain stays
at the previously accepted setting of 55. The top module has no motor calls.
Body execution, calibration, torque release and post-execution ACKs retain the
existing executor and protocol.

## Time and storage

Reminders use the aware host clock and configured IANA timezone. Relative delays
are elapsed time; tomorrow is a local calendar date. Missing/ambiguous times,
past deadlines and DST gaps/folds require clarification. A voice clarification
is promoted only after completed playback and expires after 120 seconds. Fresh
clock context accompanies every reasoning turn. UTC deadlines and their original
timezone are persisted; startup/wake claims overdue rows atomically.

A due robot alert is marked attempted before playback, delivered only after its
correlated physical proof. Uncertain delivery cannot create an automatic speech
replay loop. Due rows stay visible until an explicit dismiss/cancel/snooze. Robot
alerts wait for an idle media lane and a stopped game; Windows alerts are local.
Focus/break creation is bounded and explicit. A stable focus-break key prevents
duplicate breaks from repeated clicks.

The context schema moves from v1 to v2 after a SQLite backup to
`context-before-utilities.sqlite3`. Existing notes/tasks remain intact. New tables
hold reminders, projects and checklist/note entries. Images are transient until
explicitly saved to an existing project. A save settles both PNG and note; failed
writes clean up the PNG. Camera content is excluded from diagnostic exports.

## Top hardware

The twelve LEDs use PY32 address 0x6f, expander pin 13 and high-byte bit 5. This is
not ESP32 GPIO13 (audio). Register updates preserve the servo-power low byte.
The count is twelve; RGB565 little-endian values go to LED RAM before refresh.
Si12T address 0x68 supplies three two-bit top touch zones. Initialization, polling
and strip writes are integrated into the existing presentation task and I2C bus.
Settings use namespace `kade_ui`; settled saves reserve the media lane to avoid
flash writes during capture or playback. Camera indication takes visual priority.
LED Memory is bounded to 24 rounds with explicit start/stop, top-zone input,
optional notes, timeout and a stored best score. It has no separate I2S owner.

Official references:

- [M5Stack StackChan specifications](https://docs.m5stack.com/en/StackChan)
- [RGB example](https://docs.m5stack.com/en/arduino/stackchan/rgb)
- [Touch example](https://docs.m5stack.com/en/arduino/stackchan/touchsensor)
- [Camera example](https://docs.m5stack.com/en/arduino/stackchan/camera)
- [StackChan BSP](https://github.com/m5stack/StackChan-BSP/blob/main/src/M5StackChan.cpp)

## Camera and authenticated media

The camera uses public IDF 5.5.4 `esp_driver_cam` DVP APIs, `esp_cam_sensor` 1.5.2
and `esp_sccb_intf` 0.0.9. GC0308 control adds a device on the existing SDA12/SCL11
bus, without deleting/recreating that bus. The fixed format is 320×240 RGB565;
one user frame is 153,600 bytes in PSRAM. The driver has a warm-up backup buffer.
After a bounded warm-up, one frame is offered through ISR callbacks and a queue.
Cancellation is checked at 50 ms intervals while waiting. Stream/controller
resources are stopped and freed before audio playback. If DMA stop is uncertain,
metadata and DMA memory are quarantined until reset, never freed while active.

The bounded media extensions are:

| Path | Authentication and result |
|---|---|
| Voice | Existing `KDV2` with a fresh 128-bit token, Opus uplink and `KDR1` PCM reply. |
| Reminder alert | `KDA1` plus token; prepared `KDR1` PCM, without microphone capture. |
| Desktop snapshot | `KDC1` plus token; `KDI1` plus network-order width/height/size and RGB565 bytes; host `KDAK` receipt. |
| Explicit voice look | At most one `KDQ1` camera request within the already authenticated voice session, followed by `KDI1`/`KDI0`, then speech. |

The fixed dimensions and length are validated before reading frame bytes.
Unauthenticated, stale, duplicate and unexpected media connections cannot claim a
turn. The host requires both transfer and correlated device capture/playback,
handoff and torque-release proof before reporting success. There is no continuous
camera stream. Local QR data never become actions. Gemini descriptions use a
bounded Interactions request with `store:false`; they do not identify people.

## Verification and packaging

The host suite covers reminder dates and DST, clarification after playback,
restart persistence, concurrent due claims, uncertain alert delivery, provider
failure, existing tool confirmation, camera authentication and size rejection,
real Qt-to-worker IPC, refresh stability, lifecycle and diagnostic/credential
separation. Windows additionally exercises a unique fake Credential Manager entry
and removes it afterwards. Native sanitizer checks cover the avatar, Wi-Fi state,
top gestures, the complete 24-round game and gain/no-amplification behaviour.
The existing CP23, A4, voice cancellation, self-init, Phase B and voice-wire gates
remain required.

GitHub Actions builds firmware with IDF 5.5.4, tests Windows host Python 3.12/3.14,
and builds the desktop with Python 3.12. Desktop packaging depends on successful
host and firmware jobs. A frozen executable smoke check starts the actual private
worker, checks embedded source identity, schedules a reminder, calculates a unit
conversion and quits cleanly without credentials/hardware. The combined ZIP has
one full source commit, nested firmware hashes and a complete SHA256 manifest.
The flash layout remains bootloader 0, table 0x8000, optional OTA-init 0xd000 and
application 0x10000, with a 4 MiB application slot. No calibration erase is added.

## Owner hardware check

After flashing the complete matched RC2 package and starting the desktop:

1. Complete one ordinary front-touch voice turn; check both strips during thinking
   and a smooth spoken reply with the familiar avatar/body/idle behaviour.
2. Try top swipes and one hold; check the acknowledged Windows volume/mute. Reverse
   direction if preferred. Repeat during speech, then front-touch cancel.
3. Schedule a short reminder while connected, another while the server is stopped,
   and a date-aware “tomorrow” reminder. Confirm readback and the due list. Leave a
   due reminder visible through Quit/reopen; check no repeated alert storm.
4. Start LED Memory, repeat a few zones and stop from the front screen. Confirm
   normal top volume and voice resume afterwards.
5. Capture a well-lit object and a large QR code; check colour/orientation, cancel,
   retake, optional Gemini description, explicit project save and a normal voice
   turn afterwards. Repeat captures while watching free memory in Diagnostics.
6. Stop/restart the server and reset the robot once; check reconnection. Export the
   sanitised diagnostic report if a new hardware function needs adjustment.

Local automated and CI checks cannot establish physical strip mapping, top gesture
direction, camera colour order/exposure, camera/voice memory stability or Windows
firewall reachability on the owner's PC. Record those observations before marking
RC2 physically approved. Camera measurements precede any continuous tracking work.
