# Kadence 0.6.1 — repairs following the failed 0.6.0 desk test

0.6.0 was rejected by the owner after live testing. Its passing automated tests
did not prove the everyday bottle interaction, physical following or persona.
This update fixes those paths. It is a hardware acceptance candidate, not a
claim that retail readiness or two-second speech has been physically proved.

## What changes

- “What do I have in my hand?”, “What have I got in my hand?”, colour, visibility
  and location follow-ups request a fresh image. Spoken AUTO looks explicitly
  use UnitV2; they cannot silently switch to the built-in camera. An explicit
  saved choice of the built-in camera remains honoured.
- The image used for an answer appears on Home with its real camera source and
  capture time. Looking during tracking borrows a new frame from the existing
  camera lease and retains the target.
- Image answers receive Kadence's identity as a system instruction and answer
  the question first. Gemini conversation also receives a separate identity
  instruction. Owner vocatives use Boss, including speculative speech drafts.
- Following requires two fresh, matching native target observations, not just
  acceptance of a rectangle. During voice, target selection completes before
  the response; physical following waits for the voice lane to release.
- A follow request automatically uses the saved head setup. If an older install
  has no persisted Home, the existing 0.4.13 baseline of yaw 0°, pitch 30° is
  established with firmware 0.21.6's bounded, acknowledged move and saved only
  after execution and torque release succeed. Servo zero calibration is untouched.
- Local colour/appearance evidence rejects a native rectangle drifting onto the
  background. Loss pauses the head. A claim of theft or removal is never inferred.
- “Tell me if it gets moved” and “Watch the bottle” arm a real fifteen-minute
  stationary watch. Sustained movement or loss of sight produces one UI/voice
  notification. Occlusion is reported as loss of sight, not proof of removal.
  Stop, privacy, disconnect and expiry end the watch; it does not resume on boot.
- Awareness and greetings are enabled once during this upgrade. Camera privacy,
  the explicit source and per-person preferences remain intact. The previous
  settings are kept as camera-settings.pre-0.6.1.json. Later OFF choices persist.
- Arrival checks wait for startup camera readiness instead of being discarded.
- In AWARE mode, confirmed occupancy permits occasional small idle glances on
  the single motion lane. Voice, active camera work, tracking and privacy take
  priority. A failed physical acknowledgement pauses idle movement until reconnect.
- Reminder creation and management are advertised to the reasoning model, with
  local fast paths for common paraphrases. Task/time clarification retains context;
  a correction updates the same reminder. A unique task name can identify a
  reminder to cancel, snooze or move. Times remain resolved against the local clock.
  Observable object conditions use the actual watch. Unsupported event/location
  triggers and recurrence are explained without pretending to schedule them.
- CoreS3 0.21.7 adds a real speech detector to the microphone capture loop.
  ESP-SR's WebRTC VAD classifies each 30 ms frame; 90 ms detected speech arms a
  720 ms silence hold. All captured audio is retained through the final packet.
  Normal short pauses reset the hold. There is a three-second no-speech timeout
  and an eight-second hard ceiling. Cancellation and offline buffering are preserved.
  Device telemetry distinguishes silence, no-speech and reaching the ceiling.

## Installation and rollback

Quit Kadence completely and extract the complete ZIP.
Run Update-Robot.cmd first to install the matching CoreS3
0.21.7 firmware through its USB port. This one-time update is required for
automatic end-of-speech; a server cannot shorten the old firmware's buffered
capture. The updater verifies images, backs up NVS and verifies its preservation.
It never erases the full flash or writes calibration/storage regions. Then restart
the robot, close the updater and run Install-Kadence.cmd, which opens the new
app and creates the desktop shortcut. UnitV2 stays on 1.3.0 and SQLite on
schema 5. Do not retrain faces or reconfigure the camera.
Previous app versions and the accepted 0.4.13 fallback remain available.
The previous awareness configuration can be restored from the settings copy;
do not replace the database or onboard face files.

## Evidence and limits

Regression coverage includes the held-bottle phrases through capture, image API,
speech and completed history; the real local UnitV2 HTTP/process bridge;
acknowledged head commands; no-target rejection; a hidden blue bottle while the
native tracker still reports its old rectangle; one-shot watch alerts; startup
arrival deferral; idle priority; privacy and cancellation; and streaming speech.
The model HTTP responses and robot transport in those tests are controlled
fixtures. They prove routing and ownership, not live Gemini recognition quality,
LAN frame rate, physical mount orientation or end-to-end response time.

The accepted Alpha 1 endpoint baseline is recorded at commit b51bd76 and
`experiments/xiaozhi-backend/LATENCY_TEST.md`: server Silero with a 700 ms hold
and AFE fallback at 850 ms. The standalone rebuild removed that streaming/AFE
path and used fixed capture. This repair restores silence-driven completion
inside the present firmware; it does not claim to reintroduce the old Xiaozhi
server or to have physically revalidated its 718 ms measurement. Classifier
performance with the owner's microphone, quiet speech and room noise still
requires the device test. The endpoint controller is tested for short speech,
half-second pauses, an isolated click, no speech, long speech and turn reset.

The owner acceptance sequence is one continuous interaction: show the bottle,
ask what is in the hand and its colour, request following and move it, then ask
for notification and hide it. Check the Home image against the actual view.
Stop on unexpected head direction. Existing reversed axes are honoured when a
valid saved tracking setup exists; the legacy baseline uses the original axes.
Speech on PC/Bluetooth retains incremental playback and warm workers. Robot/Both
still use the existing complete-buffer firmware transport. Stick microphone,
volume/top-swipe defects and locomotion remain outside this update.
