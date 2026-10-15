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

## Installation and rollback

Quit Kadence completely, extract the complete ZIP and run Install-Kadence.cmd.
Use the desktop shortcut. This is a host-only update: CoreS3 stays on 0.21.6,
UnitV2 on 1.3.0 and SQLite on schema 5. Do not flash or retrain faces.
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

The owner acceptance sequence is one continuous interaction: show the bottle,
ask what is in the hand and its colour, request following and move it, then ask
for notification and hide it. Check the Home image against the actual view.
Stop on unexpected head direction. Existing reversed axes are honoured when a
valid saved tracking setup exists; the legacy baseline uses the original axes.
Speech on PC/Bluetooth retains incremental playback and warm workers. Robot/Both
still use the existing complete-buffer firmware transport. Stick microphone,
volume/top-swipe defects and locomotion remain outside this update.
