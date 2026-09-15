# Gesture, personality and audio candidate

Host 0.3.3 / firmware 0.21.4. Not yet physically signed off.

## What changed

- Kadence's provider-independent identity restores dry sarcasm, precise intelligence,
  loyal curiosity, affectionate chaos and invited roleplay. Real tool/sensor/action
  claims still require runtime evidence. Reminders and tool validation are preserved.
- Console explicitly selects Gemini or an installed Ollama model on this PC.
  No automatic cloud fallback. Existing settings default to Gemini to preserve
  working installs; select Ollama deliberately and enter its exact local model tag.
- Ollama changes reasoning only. OpenAI transcription and Edge speech still use
  online services; Windows speech synthesis fallback remains as before. Vision
  still uses its existing Gemini service. This is not a fully offline release.
- Speech output selects Robot, Windows default output, or both. Pair a Bluetooth
  speaker with Windows and select it as the default output before starting the server.
  Both may sound like an echo because the robot and Bluetooth device have different
  buffering delays; no sample-accurate synchronization is claimed.
- Windows-only output sends equal-duration silence to the robot to preserve its
  normal speaking, microphone and cancellation lifecycle. Robot microphone input
  is unchanged. Cancellation, disconnect and stop halt Windows speech as well.
- PAJ7620U2 driver on hub channel 0 validates part ID 0x7620, then applies the
  attributed DFRobot 219-register initialization incrementally. One register
  transaction per step, bounded I2C timeout 10 ms, select/readback and
  deselect/readback around each transaction. Existing discovery alternates with
  driver steps on the same worker. Failed isolated register access quarantines
  channel 0; isolation failure invalidates all channels. No voice-lane lock.
- New sensors.gesture command returns health, reading age, event counter, last
  gesture flags and event age. It is a latest-event cache, not a lossless queue.
  Polling pauses during discovery sweeps; quick gestures can be missed. Repeated
  events are limited to one per 250 ms. Flags can contain multiple gestures.
  No gesture action mappings or automatic movements are enabled.
- ToF4M remains discovery-only on channel 1. Unit ID and UnitV2 remain disconnected.

## Windows installation and check

Follow SENSOR_WINDOWS_QUICKSTART.md to pull, build and flash the current branch.
Use the new package named after the commit actually built. Keep the previous
firmware package and the working 1d4db2820820 console as fallback.
Updating source/firmware does not replace an extracted Windows executable.
Install the matching new desktop ZIP in a separate C:\KadenceX\apps folder.

For a source-run console after pulling (normal PowerShell, server stopped and quit):

```powershell
uv run --project 'C:\KadenceX\source\rebuild' --extra voice --extra desktop kadence-desktop
```

In Overview choose Thinking provider and Speech output, then Start server.
The active selection is displayed beneath the activity information. Changed
settings take effect on the next server start/restart, not during a live turn.

To find the exact existing Ollama model tag:

```powershell
ollama list
```

Start Ollama and warm the selected local model before testing. Local reasoning
shares the existing bounded conversation timeout (22 seconds); a slow cold load
can time out. Failures remain visible, without falling back to Gemini.

Persona: ask for normal banter and a short imaginary scene. Confirm useful
answers retain character and fictional actions do not become real tool claims.
Audio: Windows output first, then cancellation mid-answer, then another question.
Check a reminder through the selected output. Both is optional; prefer Windows
alone if buffering produces an echo. These physical checks remain pending.

For Gesture, stop/quit the console so COM4 is free. Keep Gesture on hub channel 0
and ToF4M on channel 1, hub at 0x70, upstream on red CoreS3 Port A. Run:

```powershell
uv run --no-project --python 3.12 --with 'pyserial>=3.5,<4' 'C:\KadenceX\source\rebuild\tools\gesture_status.py' --port COM4 --seconds 45
```

Allow boot, discovery and initialization to finish (roughly 15 seconds). When
ready/fresh, move a hand 5–15 cm in front: left/right/up/down and wave. Confirm
new event_seq values, not just the historical last flag. Restart the console
and repeat voice/cancel, camera and reminder coexistence checks before ToF ranging.

## Sources

- https://docs.m5stack.com/en/unit/Gesture
- https://github.com/DFRobot/DFRobot_PAJ7620U2 (register source blob cdd7dcf84f5e03021aa32e4aec35848495016ba5; MIT notice included)
- https://docs.m5stack.com/en/unit/id
- https://docs.m5stack.com/en/unit/unitv2_m12
- https://docs.ollama.com/api/chat

The existing CoreS3 speaker volume fault is still open. Additional audio output
must not be reported as a repair of that fault.

## Validation before publication

Local: 109 Python tests pass, 2 platform-specific checks skipped, 48 subtests;
Qt uses offscreen rendering. Sensor native gate passes under ASAN/UBSAN, with
LeakSanitizer disabled for this container. Phase B gate passes. Firmware compile
and frozen Windows packaging are delegated to the existing repository CI gates.
Physical Gesture recognition, Ollama and Windows/Bluetooth playback remain untested.

ESP32-S3 lacks Classic Bluetooth and BLE Audio support, so Bluetooth audio output
uses Windows rather than the CoreS3:
https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/ble/overview.html
