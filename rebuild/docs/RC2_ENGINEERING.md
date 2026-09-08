# RC2 engineering and qualification

RC2 implements Boss's approved first bundle: Windows console, date-aware reminders
and focus, lab workbench, deliberate visual desk assistance, both top strips,
top-touch volume and LED Memory. Quiz Night is excluded. Continuous face tracking,
enrolled-person profiles and Home Assistant actions retain their separate review
boundaries. RC1 at `997654857c3dd6aa2f78c92501c2eda2bf6744fe` remains physically
approved; this candidate does not relabel that approval as proof of new hardware.

The current maintenance candidate is **host 0.3.1 / firmware 0.21.2**. Boss approved
the Windows console's appearance, requested dependable front touch and a listening
cue, and authorised replacing the expressive face with a utilitarian green signal
display. USB control remains required; wireless control is outside this update.

## Runtime ownership

### Startup stack recovery

Firmware 0.21.1 (`b3fc07035c71`) is withdrawn: the owner's boot log reports
`A stack overflow in task main has been detected` immediately after the first
panel initialisation. The enlarged runtime frame capacity also enlarged CP16's
two local startup buffers. The compiler reserved a 2,192-byte baseline frame
across nested hardware initialisation on a 4,096-byte main task stack. The
relevant entry instructions were checked against the delivered binary.

Firmware 0.21.2 gives the fixed CP16 startup command/ACK their own 256-byte
buffers, independent of runtime frame size. The rebuilt baseline frame is 672
bytes; existing bounds checks remain in place. Main has an 8,192-byte stack.
`BOOT_STACK` lines report its minimum free
bytes after the hardware baseline and runtime initialisation. The existing
stack-overflow detector remains enabled.

CI runs `boot_stack_gate.py` after linking, before packaging. It checks the
active generated configuration and actual Xtensa function prologues, rejects
an undersized main task or excessive baseline frame, and packages a report
with the image hashes. It rejects the pre-fix image. This guards this regression;
it is not a complete worst-case call-graph proof or physical boot sign-off.

### Runtime tasks

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

## Interaction timing and signal presentation

- Front touch and top controls have one dedicated input owner with a 10 ms loop.
  Rendering has its own lower-priority task and takes a short snapshot of overlay
  data. The front-controller read has a 15 ms timeout. A 15 ms stable press triggers
  once; a 70 ms released interval and 300 ms action spacing prevent contact bounce
  and held/double taps from immediately cancelling the same request.
- One original 200 ms ascending sine cue uses the existing media worker, PSRAM
  staging, internal DMA scratch, volume ceiling and output close. It finishes
  before input opens. Mute/zero volume silence the cue without disabling the mic.
- Opus packets are staged in bounded PSRAM while recording. No socket send occurs
  with the microphone open. The fixed frame count and an elapsed-time guard bound
  capture; each codec read already has a 1 s SDK timeout. Capture failure closes
  input and reports a typed failure. The normal countdown is the configured
  2.4–8 s capture duration; the guard also allows bounded driver/scheduling overhead.
- Nonblocking TCP connect has a 10 s deadline; upload has an 8 s total budget,
  reply wait 55 s and reply download 15 s. Small incoming packets cannot renew a
  deadline. The host caps provider work at 45 s and deliberate snapshot commands
  at 45 s. Cancellation still interrupts sockets and staged local playback.
- Device `voice.phase` events correlate to the pending command. They report actual
  capture start/close and playback start. Retired phases cannot restore LISTENING.
  Confirmed cancellation retires the original host wait even if its final ACK is
  missing. Live STT/reasoning/TTS phase labels and typed diagnostics remain secret-free.
- Control frames now have a 1024-byte capacity. The full status builder is exercised
  with the same cJSON implementation as firmware and includes front touch, accepted
  touch sequence, capture time remaining, hardware state and firmware version.
- Servo send/response exchanges use one recursive transaction mutex, including a
  read's nested send, so cancel cleanup cannot consume another transaction's reply.
  Touch requests cancellation without issuing a duplicate direct UART release.
  The existing worker/control release and verification paths remain authoritative.

The display is a code-rendered green signal instrument on exact black RGB565.
Its audio amplitude reflects measured microphone/playback levels. Idle uses a
quiet cursor, recording has a countdown, and processing explicitly says MIC CLOSED
with elapsed time. The allocation-failure renderer uses the same line identity.

The supplied 8 September owner diagnostics were from `af07887c1068`: device status
was unavailable throughout, a camera attempt timed out, and two voice attempts
advanced from listening to thinking before cancellation-related failures. Those
observations do not establish successful RC2 camera or voice qualification.

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
Si12T address 0x68 supplies three two-bit top touch zones. Initialization uses
the existing I2C bus; polling and strip writes run in the dedicated input task.
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
`interaction_gate.py` adds native press/bounce/hold/rearm and cue bounds checks,
real loopback TCP stalls/trickles/cancellation, and a full cJSON status reply test.
The latter reproduces rejection at the old 384-byte limit and verifies the new
capacity, escaped correlation ID and buffer guards. Host tests cover phase
correlation, the initial arming indication and cancellation with a lost final ACK.
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

For the 0.21.2 recovery, first confirm a normal cold boot reaches the green signal
display and stays there without resetting, with the server stopped. Then start
the matched Windows console and complete one voice turn. Capture `BOOT_STACK`
watermarks if further boot investigation is needed. Resume the checks below only
after that boot and voice check; 0.21.1 must not be used as a rollback candidate.

After flashing the complete matched RC2 package and starting the desktop:

1. Wait for live device status. Tap the front screen once, wait for the cue and
   REC countdown, and speak. Confirm MIC CLOSED during processing and a smooth
   reply followed by the established body reaction and idle. Repeat five times;
   a held finger must not immediately cancel its own turn. During one capture and
   one processing wait, tap again to cancel and confirm prompt return to idle.
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
