# Kadence operator manual

**Release:** RC2 — Signal Console 0.3.2 / firmware 0.21.2

**Hardware:** M5Stack StackChan K151 / CoreS3, ESP32-S3

**Package identity:** the full source commit is in `RELEASE.json`; the included firmware and host are built from that source. Host 0.3.2 also supports the already-installed firmware 0.21.2.

Kadence combines spoken conversation and the animated terminal avatar with a
Windows control console, date-aware reminders, a lab workbench, deliberate camera
snapshots, animated top strips, touch volume and an LED memory game. This guide
covers the implemented RC2 candidate. New hardware functions await the owner's
physical check. The approved RC1 remains the rollback baseline; its acceptance
is recorded in [RC1_ACCEPTANCE.md](RC1_ACCEPTANCE.md).

## 1. Install the matched release

**Already running the stable boot recovery (firmware 0.21.2)?** Quit the old
Kadence app, including its tray icon. Extract this whole ZIP to a new folder,
open its `Kadence.exe`, and start the server. **No flash is needed.** Saved
settings, reminders and the optional Windows credential entry remain available.
Use the steps below only for a first install or older firmware.

1. Extract the **whole** `Kadence-RC2-<commit>.zip` to a new folder. Keep
   `Kadence.exe`, `_internal`, `Firmware` and the accompanying files together.
2. Quit Kadence completely, including its tray icon, and close serial monitors.
3. Connect the robot by USB and put it in download mode.
4. Open PowerShell in the extracted folder and run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Flash-Kadence.ps1 -Port COM4
   ```

5. Wait for `KADENCE_FLASH PASS`. Restart the robot normally if it remains in
   download mode. Download mode is only for flashing.
6. Open `Kadence.exe` from this same folder.

Flashing uses the existing ESP-IDF 5.5.4 installation at
`C:\Espressif\frameworks\esp-idf-v5.5.4`. Normal use of the desktop executable
includes its own Python and dependencies and needs no ESP-IDF terminal.
The flash helper verifies the package pairing and firmware hashes and preserves
calibration and stored device settings. Keep the complete approved RC1 package
and its matching source available for rollback.
The command permits the unsigned launcher for that PowerShell process only.
It does not change the saved execution policy or override an organisation's Group Policy.

## 2. Connect and control the server

In **Overview**, set the robot port, Wi-Fi network and PC LAN address. **Scan**
refreshes ports and LAN choices and can fill the current Windows Wi-Fi SSID.
`COM4` is the established port for this robot. Choose the PC address reachable
from the robot's 2.4 GHz Wi-Fi network; PC Ethernet is also suitable when it
reaches that network. The PC and robot must be able to communicate across the LAN.
Normal voice and online descriptions also need Internet access.
Keep **USB connected to the PC during normal use**, and keep the PC awake with
the server running. Wi-Fi carries audio/images; USB carries control and events.
This release does not provide cable-free operation.

Enter the OpenAI key, Gemini key and Wi-Fi password locally. Each field has its
own **Show/Hide** control. Session-only storage is the default. To reuse credentials
on this Windows account, select **Remember on this Windows account**, then start
the server. Kadence uses Windows Credential Manager. **Forget** removes its saved
entry and clears the fields; a running server retains its session values until
stopped. Ordinary settings and diagnostic exports contain no credentials.

Set **Timezone** to your IANA zone, normally `Europe/London`. The displayed local
clock and new reminders use this setting even while the robot server is stopped.
Stop the server before changing its timezone. Existing reminders keep their
original scheduled instant and timezone. Windows' date and time must be correct.

| Control or status | Operation |
|---|---|
| Start server | Starts one robot runtime with the current connection and credential fields. |
| Stop | Cancels active robot work and closes the connection. Local desktop utilities keep running. |
| Restart | Stops the current runtime before starting another with the current fields. |
| Server running | The server is available; check robot connection separately. |
| Robot connected | The robot has completed the control connection handshake. |
| Keep in tray | Closing the window hides it while local utilities and the server continue. Reopen from the tray. |
| Quit | Stops the server and local reminder service and exits the application. |

Keep Windows awake and Kadence open, or in its tray, for timely reminders. A
running server can reconnect after a robot reset. Local reminders, projects and
calculations remain available when the robot is disconnected. Without speech
credentials, direct local utilities and camera capture/QR still work; ordinary
conversation requires the configured speech providers.

## 3. Talk and cancel

1. Tap the **front touchscreen** once.
2. Wait for the short ascending two-tone cue and **REC / MIC OPEN**, then speak
   one short request. The display counts down the remaining recording time.
   Recording is 4.8 seconds by default; Overview allows 2.4–8 seconds.
3. Let Kadence finish thinking and speaking. A successful voice turn ends with
   the established body reaction and return to idle.
4. Tap again for another turn.

Tap the front screen during an active turn to cancel recording, provider work or
playback. Wait for idle before trying again. If no speech is detected, Kadence
asks you to try again. During LED Memory the front screen stops the game; tap
again after it stops to begin a conversation.
One deliberate press is enough; holding your finger does not start another turn.
The microphone closes before upload and processing. **MIC CLOSED** and an elapsed
timer distinguish processing from recording. The Windows overview also identifies
transcription, reasoning, voice connection, audio receipt and decoding.
Sonia remains the preferred voice. If her request cannot finish within 12 seconds,
Windows generates the same reply with an installed local voice. The server shows
**LOCAL VOICE** when this happens; the fallback voice may sound different.
Local speech has its own 12-second deadline, and a front touch cancels either
voice. If both fail, check the server status message before retrying.

In **Diagnostics**, **Check speech** generates a fixed test phrase and reports
whether Sonia or the Windows voice produced audio. Stop the server first. This
check uses no microphone, no API keys, and does not play audio through the PC or
robot; a normal robot voice turn checks physical playback. The black-and-green
Signal Console animation follows acknowledged device state. It is a state
indicator, not a microphone level meter.
When speaker output is muted or its volume is zero, the listening cue is silent;
use the REC indicator and countdown. Speaker mute does not disable recording.

Kadence uses OpenAI transcription, Gemini reasoning and Sonia's British female
voice by default. Up to eight successfully played exchanges are kept in bounded
session context. Stopping the robot server clears that conversational context.
Use a saved note, project record or reminder for information that must survive.
Each reasoning turn receives fresh local date/time context.

## 4. Avatar, strips and volume

The robot uses a utilitarian signal display on a solid black background, with
green terminal lettering and an animated waveform. Listening and playback drive
the signal amplitude from actual audio levels. Idle uses a quiet sweep; processing
has its own animation and elapsed timer. Display animation remains local and
touch input runs independently of drawing. Overview reflects device activity.

| Indication | Meaning |
|---|---|
| Ready / arming | Standby or preparation before the listening cue. |
| REC / MIC OPEN | Recording with a countdown; both top strips show a steady listening colour. |
| Thinking / tool working | Green movement travels along both strips. |
| Speaking | Strip intensity responds to the playback level. |
| Camera active | Amber strips and a screen label identify a requested capture. |
| Volume bar / muted | Brief strip and screen feedback follows a volume gesture. |
| Offline / degraded / fault / recovery | A connection or operation is unavailable or recovering. |

In **Device / Play**, use the volume slider, **Mute**, or a **Volume ceiling**.
The displayed numeric level comes back from the robot. Level 100 is the existing
maximum speaker level. A lower ceiling limits both desktop and touch adjustment.

Slide across the three **top sensor zones** to change volume by five points.
The opposite direction reduces it. Use **Reverse swipe direction** if you prefer
the physical direction reversed. Hold still for about 1.2 seconds to toggle mute;
release before the next gesture. Muting preserves the selected volume. These
controls also work during playback. Front-screen talk/cancel remains separate.

Set strip brightness from 0–60 and select **Dark when idle** as desired. A camera
indicator retains a small minimum brightness during capture. Device settings and
the game's best score are saved after about five settled seconds; leave the
robot powered briefly after changing them.

## 5. Reminders, timers and focus

Use the **Reminders** page to enter a short task and a time, then select
**Schedule**. The result reads back the actual date, time and timezone. If Kadence
asks a date/time question, type the answer and select **Answer**. A clarification
expires after two minutes; enter the full request again if it expires.

You can also use voice:

| Request | Behaviour |
|---|---|
| “Remind me at 7 pm to check the print.” | Schedules today at 19:00 if that time is still ahead. |
| “Tomorrow remind me I need to order filament.” | Asks what time tomorrow; answer in the next touch-initiated turn. |
| “Remind me tomorrow at nine am to order filament.” | Uses tomorrow's local calendar date and reads back 09:00. |
| “Remind me to check the print in twenty minutes.” | Starts a named countdown. |
| “Set a timer for five minutes.” | Schedules a timer notification. |
| “Read my reminders.” | Reads up to five active reminders with IDs and scheduled times. |
| “Snooze reminder one for five minutes.” | Reschedules that active reminder. |
| “Cancel reminder one.” / “Dismiss reminder one.” | Removes it from the active list. |
| “Start a twenty-five minute focus.” | Starts a focus session with a completion reminder. |

Supported time expressions include `tomorrow`, `today`, named weekdays,
`19:30`, `9 am`, `noon`, `half past seven pm`, `25 December 2026`,
`25/12/2026`, `2026-12-25`, and delays in seconds, minutes, hours or days.
Named weekdays mean their next occurrence. A missing time, an ambiguous `7`, a
past time or a daylight-saving gap/repeated hour requires clarification. For an
unambiguous morning clock entry use `09:00` or `9 am`. No default reminder time
is silently chosen. Deadlines can be five seconds to one year ahead.

“Tomorrow” follows the selected local calendar. A relative “in a day” means
24 elapsed hours; these differ around clock changes. Reminders persist as UTC
instants with their timezone and survive application restarts. Unheard or
cancelled voice clarification questions do not remain pending.

When due, a reminder stays highlighted until dismissed, cancelled or snoozed.
Windows provides a local sound and, when available, a tray notification. The robot
waits until voice, camera and games are idle, then gives one combined notification.
If speech is unavailable it can play a local chime. Missed reminders remain
visible after restart/wake. An uncertain robot delivery is not automatically
replayed. The Reminders page remains the authoritative list.

For focus, choose 1–180 minutes and **Begin focus**. When the focus reminder is
due, select it and choose **Start break** for five minutes. Starting the break
dismisses that focus reminder. Start another focus session when ready. Sessions
do not repeat automatically. Up to 200 active reminders are supported.

## 6. Lab workbench

In **Workbench**, create or select a project. Add a **Note** for a finding or a
**Step** for a checklist action. Select a step and choose **Mark done**. Search
narrows that project's records by text; completed steps remain available. **Delete**
asks before removing a selected record.

Voice can create a project, add notes/steps, read a project by its exact name and
complete returned checklist entry IDs. For example: “Create a project called
Sensor bench”, “Add a step to Sensor bench: measure idle current”, or “Read the
Sensor bench checklist”. Proposed stored changes are read back for confirmation.
Answer “Yes” in the next completed voice turn within 60 seconds.

The calculator offers arithmetic, unit conversions, Ohm's law and four/five-band
resistors. Enter the input shown beneath its selector, then calculate:

| Mode | Input example |
|---|---|
| Arithmetic | `(12 + 3) * 4` |
| Conversion | `1`, from `in` to `mm` gives `25.4 mm`. |
| Ohm's law | `V=5, R=1000` gives current and power as well as voltage/resistance. |
| Resistor bands | `yellow, violet, red, gold` gives 4,700 ohms ±5%. |

Ohm's law requires exactly two positive values: volts, amperes and ohms. Unit
conversions cover length, mass, volume, temperature, voltage, current and resistance.
Resistance units use explicit `megohm` and `milliohm` names. Resistor band order
must be supplied by the user. These calculations are deterministic and run locally.
There are limits of 100 projects and 5,000 project records, each up to 800 characters;
a project view returns up to 250 matching records.

## 7. Visual desk assistant

In **Vision**, select **Capture** for one 320×240 camera image. Capture is allowed
when the robot is idle. The preview and local QR result appear in Windows. **Cancel**
stops an active camera operation; **Clear** releases the transient preview/result.
QR contents are displayed as text and are never opened or executed automatically.

After capture, enter a short question if desired and choose **Describe with Gemini**.
This deliberately sends that image to Gemini for common objects or readable labels.
Local capture and QR decoding need no Gemini key. An ordinary voice request such
as “What am I holding?” or “Look at this and read the label” can request one image
within that voice turn, followed by a spoken description.

Use good lighting and hold the object steady. Common objects and large labels are
suitable first checks. Small component markings, distant labels and tiny QR codes
may exceed the camera's useful detail. Descriptions should express uncertainty.

Images remain temporary unless you select a project and choose **Save observation**.
Saving retains a PNG and a timestamped project note with the current description.
Clearing the preview does not delete saved observations. Saved PNGs live in the
`observations` data folder; deleting a project note does not remove its PNG.
Continuous video, face tracking and enrolled-person recognition remain a later
camera qualification stage.

## 8. LED Memory

In **Device / Play**, choose **Play memory** with the robot idle. Watch the
sequence, then repeat it by tapping and releasing the three top zones.

- Red corresponds to zone 1, green to zone 2 and blue to zone 3.
- Each successful round adds a step. The score is the number of completed rounds.
- An incorrect zone or 20 seconds without the next input ends the round.
- A session has a maximum of 24 rounds. Best score is stored on the robot.
- Toggle **Sound cues** for optional short notes.
- Select **Stop game** or touch the front screen to stop.

During this explicit game, top taps are game inputs. Volume gestures resume when
it finishes. Set some strip brightness before starting. The quiz is excluded.

## 9. Existing companion utilities

The previously approved features remain available through voice:

| Feature | Example |
|---|---|
| Date/time | “What time is it?” / “What day is it?” / “What time is it in Tokyo?” |
| General arithmetic | “Calculate eighteen times twenty-four.” |
| Saved notes | “Remember that the spare cables are in the blue drawer.” |
| Recall/search | “Read my notes.” / “Search my notes about cables.” |
| Delete a note | “Delete note three.” Then confirm. |
| To-do list | “Add replace the printer filament to my list.” / “Read my list.” |
| Complete a to-do | “Mark item four as done.” Then confirm. |
| Weather | “What is tomorrow's forecast for Bristol, England?” |
| Home status | “What is the status of my home?” with Home Assistant configured. |

Direct “Remember that…”, “Remember this…”, “Make a note…” and “Add … to my list”
requests authorise the local addition. Deletions, completions and other proposed
stored changes ask for confirmation; answer within 60 seconds in a new voice
turn. Cancellation, disconnection or a change of topic discards the proposal.
Read a list before retrying a write whose outcome was not confirmed.

Legacy notes/tasks support 1,000 records of up to 800 characters. Spoken lists
return at most five items. Completed tasks remain stored. Note editing, reopening
completed tasks and purging completed records are not current voice operations.
To-do items are separate from timed reminders.

Weather uses Open-Meteo without an API key, covers today through six days ahead,
and reports Celsius, daily high/low and precipitation probability. Use a full
location if a place name is ambiguous. Home Assistant remains read-only and
returns only configured entities.

## 10. Diagnostics and data

**Diagnostics** shows connection/activity events, available device memory,
completed-turn counts, bounded failure stages and STT/reasoning/TTS durations. **Export diagnostics** saves
only selected status fields and package identity, excluding credentials,
conversation text, images, QR contents and saved notes.

The Windows data directory is `%LOCALAPPDATA%\Kadence`, unless overridden by
`KADENCE_DATA_DIR`. It contains `context.sqlite3`, ordinary desktop preferences
and any explicitly saved `observations` images. The first RC2 store migration
creates `context-before-utilities.sqlite3` and preserves RC1 notes/tasks. To back
up or restore, quit Kadence and copy the complete data directory. Retain that
migration backup when returning to the older RC1 host.

Kadence does not automatically save recordings, transcripts or camera images.
Voice sends microphone audio to OpenAI, request context to Gemini when needed,
and reply text to the speech service. Selected saved records can enter that
context. Describing an image sends the requested image to Gemini. Direct local
utilities, local QR and device presence remain independent of those services.

## 11. Source/terminal operation and optional configuration

For a matching source checkout, install `rebuild[voice,vision]` into the selected
Python 3.12+ environment and run:

```powershell
python -m kcore.appliance --visible-input
```

Omit `--visible-input` to hide local credential entry. `kadence` invokes the same
runtime. `Ctrl+C` stops it. The source desktop entry is `kadence-desktop` after
installing `rebuild[voice,desktop]`. Run one host at a time.

| Source runtime option | Default / purpose |
|---|---|
| `--port`, `--baud` | `COM4`, `115200`. |
| `--capture-ms` | `4800`; 2400–8000 allowed. |
| `--reconnect-delay` | `2` seconds. |
| `--check` | Checks dependencies/timezone without hardware or credentials. |
| `KADENCE_WIFI_SSID`, `KADENCE_WIFI_PASSWORD` | Process Wi-Fi input; otherwise detected/prompted. |
| `KADENCE_LAN_HOST` | Reachable PC LAN IPv4 address override. |
| `KADENCE_TIMEZONE` | `Europe/London`. The desktop uses its Overview setting. |
| `KADENCE_DATA_DIR` | Alternate local storage directory. |
| `OPENAI_API_KEY` | Process transcription credential. Desktop credentials use its fields/vault. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Process reasoning credential. |
| `KADENCE_STT_MODEL` | `gpt-transcribe`. |
| `KADENCE_THINKER_MODEL` | `gemini-3.5-flash-lite`. |
| `KADENCE_TTS_VOICE`, `KADENCE_TTS_RATE` | `en-GB-SoniaNeural`, `+0%`. |

Provider/model overrides above apply to the source CLI. The packaged desktop uses
the release defaults. Enter credentials in local prompts/fields, not command
history or shared logs.

For optional read-only Home Assistant, supply `KADENCE_HA_URL` (base URL),
`KADENCE_HA_TOKEN` and `KADENCE_HA_ENTITIES` (up to eight comma-separated IDs)
before launching Kadence. Omit all three if unused. No device/scene actions are
included.

Source deployment remains available through `rebuild/tools/deploy.ps1`. A supplied
firmware-only ZIP must match the updated checkout's **full commit**, including
documentation commits. Preserve that check. The complete desktop ZIP instead
carries its own matched executable and firmware and uses `Flash-Kadence.ps1`.
