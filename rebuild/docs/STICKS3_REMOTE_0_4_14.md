# Kadence 0.4.14 — StickS3 Remote V1 and shared Motion home

The robot stays on firmware 0.21.6 and its existing tether. UnitV2 stays on service
1.2.0. Flash only the **StickS3**, using the separate remote image. Remote starts
OFF. Wireless robot transport and gyro control are explicitly unavailable in V1.
Colour/shape recognition remains future work using the original UnitV2 programs.

## Stick microphone correction — firmware 1.0.2

The owner confirmed boot, steady display and successful pairing, but remote PTT
returned "Sorry, I didn't catch that." The pinned M5Unified 0.2.12 defines the
StickS3 ES8311 microphone enable callback but never assigns it to the StickS3
microphone configuration. I2S setup can succeed without enabling the codec ADC.
Firmware 1.0.2 pins upstream M5Unified 0.2.13, which assigns that callback. The
packaging gate now rejects a driver that defines but does not attach the callback.

While holding A, the main screen shows an **IN** level in dBFS and a bar derived
from the exact outgoing PCM with DC offset removed. It should respond to speech;
it measures electrical sample level, not calibrated sound pressure or recognition
confidence. Menu -> Mic / Status retains the highest frame RMS level and sent-frame
count from the last capture and shows firmware 1.0.2. No samples are retained for
this meter. The protocol and installed host 0.4.14 are unchanged; flash only Stick,
retain DIO settings, do not erase all flash or re-pair an already paired device.
After flashing, hold A, wait for LISTENING, speak normally, and release. Confirm
both a responding input meter and a correctly transcribed/replied-to utterance.
Actual microphone/recognition acceptance remains a hardware check.

## Stick boot-image correction — packaging revision 2

The first 0.4.14 package incorrectly forced QIO into the ROM boot header while
merging the binaries. Hardware showed repeated `mode:QIO`, `ets_loader.c 78` and
watchdog resets before application startup. The compiled bootloader already uses
DIO; packaging revision 2 preserves it byte-for-byte, along with every other image
component. The new packaging gate rejects any changed component or non-DIO header.
Firmware 1.0.1 also renders each frame into a PSRAM canvas before pushing it to
the LCD. This removes the visible black-clear/text-redraw cycle at each refresh.
Protocol remains 1; host installation need not change. The owner confirmed that
the explicit DIO reflash boots, then reported the original screen flicker.

Recover the first image using Espressif's browser flasher: enter download mode,
disconnect its Console, connect under Program at 115200 baud, select the merged
`kadence-sticks3.bin` at address `0x0`, and explicitly select Flash Mode **DIO**,
Flash Frequency **80m**, Flash Size **8MB**. Program, disconnect and press reset
once. No whole-chip erase is needed. With the corrected revision 2 image, keep
the image's flash settings (or explicitly select DIO); do not override to QIO.
The application's qio_opi flash/PSRAM configuration is separate and unchanged.
Buffered display and remote acceptance must still be confirmed on the owner's Stick.

## Install

1. Quit Kadence. Extract the complete desktop ZIP and run Install-Kadence.cmd.
2. Unplug the CoreS3 robot USB cable so it cannot be selected by mistake. Connect
   only the StickS3. Run Flash-StickS3.cmd from the extracted package, select its
   COM port and type STICK. This replaces the Stick's current firmware. It does
   not flash the robot or the UnitV2. The supplied image is checksum-checked.
   If the Stick will not enter download mode automatically, use its reset/download
   procedure and retry. The normal firmware and bootloader are included in one
   image at offset 0x0; do not use a CoreS3 image.
3. Reconnect the robot, open the installed Kadence, check the Wi-Fi credentials
   and PC LAN address in Overview, and start the server as usual.
4. Device → enter the **Stick USB COM port** → PAIR STICK VIA USB. The helper
   requires the firmware to identify itself as a Kadence StickS3 before sending
   Wi-Fi and pairing data. The selected port must differ from the active robot.
5. Device → REMOTE ON. The Stick connects over the same local Wi-Fi network.
   The server displays the endpoint, connection, RSSI and microphone state.
   Unplug the Stick USB cable to use its battery. The robot remains tethered.
6. If Windows blocks the new installed executable, use the existing Overview
   **ALLOW ROBOT AUDIO** helper on the private LAN. Its application-specific
   private-subnet rule also covers the remote port. No router port forwarding.

Pairing saves Wi-Fi credentials and a random device key on the Stick, and the
matching key in the Windows user's Kadence data directory. Pairing again replaces
that authorization. The key is not displayed or placed in diagnostic exports.
To change Wi-Fi or PC IP, pair again over USB. A DHCP reservation for the PC avoids
having to re-pair when its address changes. Server restart leaves Remote OFF.

## Stick controls

- Main screen: **hold A** to talk, **release A** to send; **tap B** opens the menu.
- Menu: tap A next; tap B previous; hold A select; hold B back/exit.
- Camera menu is populated from the server: Privacy on/off, On demand, Keep ready,
  Stop camera, Perception on/off. Lifecycle/Privacy checks still apply. It does not
  fabricate unsupported colour, shape or monitoring states.
- Microphone/Status and Network/Status show live server/network state. Gyro is
  labelled unavailable; there is no hidden or automatically armed motor control.
- Replies play through the existing selected output: robot, Windows or both.
  The Stick is a microphone/control client, not a second speaker or AI service.
- Display mirroring means structured state, not video or the robot framebuffer.

PTT has **no duration cutoff**. Five, twenty and sixty seconds are valid, as are
longer deliberately held captures. The four-second-class robot capture policy is
unchanged. Release is required before transcription/conversation starts. Audio is
spooled to temporary storage on the PC; it is discarded after completion or
failure. Thirty-second uploads with half-second overlap keep provider request
size bounded while preserving the full utterance. The existing STT, conversation,
tools and TTS implementation handles the result. Longer recordings take longer
to transcribe. Storage exhaustion produces an explicit failure, not a silent cut.

Remote OFF, disconnect, malformed audio, missing frames, a two-second audio
watchdog or explicit cancellation discards an unfinished capture. It is never
silently submitted as a partial command. One microphone/voice owner exists at a
time; robot touch and other camera work cannot start a competing turn. Remote
failure does not close the robot serial connection. Restart/reconnect uses a fresh
server snapshot and a fresh capture; audio is never replayed automatically.

## Motion and one shared Home

Vision → **Motion**, immediately next to Tracking, provides:

- Yaw/pitch fields and **MOVE TO POSE** to check a comfortable position.
- **SET HOME** moves to the selected position, waits for the existing firmware's
  acknowledgement of reached position and released torque, then saves it.
- **HOME** returns to that saved position. Tracking's RETURN HOME and MOVE HOME &
  ARM use exactly the same saved coordinates. No tab keeps an independent home.
- **STOP / DISARM** stops further tracking movement. An already issued firmware
  movement must finish and release torque before the operation completes.

Home persists across server restarts, with no automatic startup movement. The
position is a user-selected target confirmed by the existing firmware's movement
contract, **not continuously sampled servo telemetry**. Set Home does not infer a
manually pushed physical pose or rewrite servo zero calibration. Choose the pose
in the fields. Coordinates use the existing limits: yaw -32..32°, pitch 3..87°.
Tracking stays within its ±18°/±15° window around shared home **and** those hard
limits. It still needs the UnitV2 on the moving head and explicit arming.

## Protocol v1

WebSocket `ws://<selected-PC-LAN-IPv4>:8766/kadence/v1`. No wildcard bind. The
trusted-LAN channel is not encrypted; audio and state must stay on your private
network. Pairing is required; the endpoint exposes no shell, database or model API.

Server sends `remote.challenge` with a random 64-hex nonce. Client sends:
`{v:1,type:remote.hello,device:StickS3,device_id:<16hex>,proof:<64hex HMAC>}`.
Proof is HMAC-SHA256 using the raw 32-byte pairing key over ASCII
`1:<nonce>:<device_id>`. Fresh nonce per connection; five-second handshake deadline.
Only one authenticated client may own the session. Browser Origin is rejected.

After `remote.accept`, receive `state.snapshot` every 500 ms. The snapshot includes
robot_link=tethered, actual connection, operational state, camera state/source,
mic source/state, RSSI and capabilities. Future clients can reuse this protocol.

Client JSON commands use `{v:1,seq:<consecutive integer starting 1>,type:...}`:

| Type | Additional fields | Result |
|---|---|---|
| remote.ping | rssi (-127..0) | Connection metadata |
| audio.start | none | capture ID, 16000 Hz, 640 samples/frame |
| audio.stop | capture, frames | Validate and process completed capture |
| camera.set | command (advertised key) | Result from existing camera authority |

Binary audio is a 32-bit big-endian capture ID, 32-bit big-endian sequence starting
0, then exactly 640 mono signed little-endian PCM16 samples (40 ms). Sequence gaps,
wrong capture IDs, surplus fields, invalid sizes and excessive rates are rejected.
JSON results carry the original seq and ok/message. Errors are explicit. WebSocket
queues and messages are bounded; slow/dead peers are closed. Gyro is not advertised.

## Build and rollback

Source branch: `kadence/sticks3-remote`. Preserved baseline branch:
`kadence/baseline-0.4.13` at `1809efb48cfdd2356858e406486d19bccc2c03b6`.
The owner reported 0.4.13 worked quite well; that is not a new exhaustive hardware
sign-off. Baseline software: 361 tests/119 subtests passed, six environment skips.

Stick: Python 3.12; `pip install platformio==6.1.18`, then
`python rebuild/tools/package_sticks3.py --source-commit <full-current-commit>`.
Exact platform/library versions are in rebuild/sticks3/platformio.ini. Build emits
rebuild/dist/StickS3 with merged image, checksum/source manifest and licence files.
No Wi-Fi credentials or pairing keys are compiled into the image.

Host: use the existing Windows workflow. It builds the Stick first, runs host
regressions, then bundles the matching image and installer in the desktop package.
The executable includes its flash utility; everyday use needs no Python install.

Rollback: turn Remote OFF, close 0.4.14 and install the preserved 0.4.13 package.
Robot firmware, UnitV2 native face profiles and camera service are unchanged.
The new motion-home.json and remote-pairing.json are ignored by the old host.

## Acceptance checklist

Automated evidence is recorded in the integration handover after the release run.
Hardware-only checks remain pending until performed on your Stick/robot:

1. Remote OFF: robot voice, sensors, native recognition and tracking still work.
2. Pair/ON: Stick shows current server state and recovers after Wi-Fi loss.
3. Hold A for 5, 20 and 60 seconds; release. Verify the complete question and one
   reply through the selected output. Confirm there is no four-second cutoff.
4. During PTT, turn Remote OFF or disconnect Wi-Fi. No partial command runs;
   robot touch voice still works afterward. Reconnect requires a fresh press.
5. Test A/B menu and Privacy/On demand/Stop; compare server-authoritative state.
6. Motion: select a safe small pose, Set Home, change pose, press Home in Motion
   and Tracking. Both return to the saved home. Restart and repeat.
7. Keep the accepted voice/face/tracking baseline until these physical checks pass.

Next wireless phase: add an explicit transport interface around the existing
RuntimeBody/host owner, then a Wi-Fi robot adapter with a deliberate close-before-
open handover. Never auto-fallback and never reuse the remote socket as an
unauthenticated robot command channel. Optional IMU/dead-man control remains a
separate bounded consumer of Motion, after remote microphone hardware acceptance.

## Implementation evidence matrix

| Requirement | Automated evidence | Physical acceptance |
|---|---|---|
| Recoverable baseline | Preserved remote branch and baseline regression | Owner said tracking worked quite well |
| Tether unchanged; Remote OFF | Existing voice/runtime ownership gates; OFF default check | Repeat normal voice/sensor/face operation |
| Paired endpoint and reconnect | Real WebSocket HMAC, rejected replay/second client, fresh session | Stick Wi-Fi loss/reconnect and RSSI |
| Long PTT; common pipeline | 60-second spool and bounded uploads; >4-second WebSocket release reaches shared function | 5/20/60-second spoken questions |
| OFF/disconnect/watchdog | Capture and processing cancellation; no partial execution/serial reset | Switch OFF and drop Wi-Fi while holding A |
| Camera authority | Existing command handler, failed lifecycle result preserved | Compare camera menu results with console |
| State/menu | Firmware compiled; server snapshot and capabilities validated | Buttons, display, microphone quality |
| Shared Motion home | Persistence, matching Tracking coordinates, failed ACK, cancellation and Stop-race tests | Both Home buttons and restart persistence |
| Gyro | Explicitly unavailable, capability false | Deferred per optional scope |
| Wireless robot | Explicitly unavailable; no auto-failover path | Later phase |

The test fixtures do not prove Stick microphone sensitivity, playback audibility,
button feel, Wi-Fi range, motor direction or online transcription quality.
