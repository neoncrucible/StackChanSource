# Kadence operator manual

**Approved build:** RC1, host 0.2.0 / firmware 0.20.1

**Approved source:** `997654857c3dd6aa2f78c92501c2eda2bf6744fe`

**Hardware:** M5Stack StackChan K151 / CoreS3

**Owner approval:** 7 September 2026

Kadence is a desktop companion with a local animated avatar, spoken conversation,
saved notes, a to-do list, time and arithmetic tools, weather forecasts, and an
optional Home Assistant status connection. This manual describes the features
in the approved build. The [acceptance record](RC1_ACCEPTANCE.md) identifies the
observed hardware run and the approved source.

## 1. Start Kadence

Keep the robot connected to the Windows PC by USB. The PC and robot also need
LAN access to each other over the robot's 2.4 GHz Wi-Fi network. Internet access
is required for the normal speech services. Leave the robot in normal boot mode
for everyday use; download mode is only for flashing firmware.

Open PowerShell in the installed source folder and run:

```powershell
cd C:\KadenceX\source
python -m kcore.appliance --visible-input
```

Enter the OpenAI API key, Gemini API key and Wi-Fi password when requested.
`--visible-input` displays what you type in your local terminal. To hide credential
entry, use `python -m kcore.appliance` without that option. `kadence` is also an
installed command for the same application; the module command uses the Python
selected in the current terminal.

Kadence normally detects the PC's Wi-Fi network name. If it cannot, it asks for
the SSID. Credentials supplied at the prompts are held for the running process.
The robot holds its Wi-Fi settings in RAM. Enter credentials only on your PC;
omit credential prompts and their contents from any log you share.

Wait for:

```text
KADENCE_RUNTIME DEVICE ready presence=local
```

The preceding `KADENCE_RUNTIME READY` line identifies the control port and LAN
listener. `DEVICE ready` means the host has also connected to the robot.

## 2. Talk, cancel and stop

1. Tap the front touchscreen once to start a turn.
2. Wait for the listening indication, then speak. The default recording window
   is 4.8 seconds, so use one short request at a time.
3. Allow Kadence to think and finish speaking. A small body reaction follows a
   successful turn, then the robot returns to idle.
4. Tap again to begin another turn. You can continue without restarting the host.

Tap the touchscreen during an active turn to cancel it. This also works while
Kadence is waiting for a reply or playing speech. Let the robot return to its
ready state before starting again. If no speech is detected, Kadence gives a
short spoken invitation to try again.

Press **Ctrl+C** in PowerShell to stop the server. A completed shutdown reports:

```text
KADENCE_RUNTIME STOPPED clean=1
```

The next startup uses the same command. Stop Kadence before flashing or opening
a separate serial monitor. If the robot resets while the host remains running,
the host automatically attempts to reconnect.

## 3. Avatar and status display

The approved presentation uses a solid black background, green terminal styling,
monospaced labels and the animated avatar. Gaze, blinking, attention and audio
response are rendered on the device. Local idle presence continues independently
of the time taken by the host or a speech provider.

| State | Meaning |
|---|---|
| Booting | The local presentation is starting. |
| Idle | Kadence is resting between interactions. |
| Attentive | Local touch attention is active. |
| Listening | The microphone is recording this turn. |
| Thinking | Kadence is preparing or processing the turn. |
| Speaking | The robot is playing the prepared spoken response. |
| Tool working | A registered utility is running. |
| Offline | A required connection is unavailable. |
| Degraded | Part of the service is unavailable. |
| Fault | An operation cannot complete normally. |
| Recovery | Kadence is returning to an available state. |

These are presentation states; the terminal provides the more detailed connection
and turn status. A completed ordinary turn reports `voice=1 body_reaction=1
idle_return=1`.

## 4. Conversation and short-term context

Ask questions, discuss an idea, request a short explanation or continue the
previous topic. Kadence uses a consistent conversational identity and British
female voice. The current defaults are OpenAI transcription, Gemini reasoning
and Edge speech with the Sonia voice.

Kadence retains up to eight completed exchanges within the running session,
subject to a total text limit. Only successfully played turns enter that history.
Stopping the host clears this conversational context. Use an explicit saved note
for information you want available after a restart.

## 5. Current utilities

Examples below are short enough for ordinary voice turns. Give one request at a
time. Where a result contains a numbered item, use that returned number for a
later change.

| Feature | Example request | Result |
|---|---|---|
| Local date and time | “What time is it?” / “What day is it?” | Current time and date in the configured timezone. |
| Time in another timezone | “What time is it in Tokyo?” | The clock tool can use another IANA timezone. |
| Arithmetic | “Calculate eighteen times twenty-four.” | A calculated numeric result. |
| Save a note | “Remember that the spare cables are in the blue drawer.” | Saves a numbered local note. |
| Read notes | “Read my notes.” | Reads recent saved notes and their IDs. |
| Find a note | “Search my notes about cables.” | Searches saved text by a literal keyword or phrase. |
| Delete a note | “Delete note three.” | Asks you to confirm deletion of the identified note. |
| Add a task | “Add replace the printer filament to my list.” | Saves a numbered to-do item. |
| Read tasks | “Read my list.” | Reads unfinished items and their IDs. |
| Complete a task | “Mark item four as done.” | Asks you to confirm the identified item. |
| Weather | “What is tomorrow's forecast for Bristol, England?” | Daily high, low and precipitation probability, with Open-Meteo attribution. |
| Home Assistant status, when configured | “What is the status of my home?” | Reads only the configured entities. |

Arithmetic supports numbers, parentheses, addition, subtraction, multiplication,
division, remainder and bounded powers. It does not execute code. Weather covers
today and up to six days ahead, reports Celsius, and may ask for town, region or
country to distinguish places with the same name. In that case, repeat the full
weather request with the more specific location.

Saved notes and tasks are available through the local store. The store allows
up to 1,000 records of at most 800 characters each, including completed tasks.
Spoken lists return at most five items per response; keyword searches help narrow
longer collections. Completing a task removes it from the unfinished list but
does not delete its stored record. The current voice tools do not edit note text,
reopen completed tasks or purge completed records.

The to-do list stores items for later retrieval. It does not yet schedule alarms
or reminder notifications. Home Assistant access is currently read-only; it does
not switch devices or run scenes.

## 6. Confirm a change

A direct request beginning “Remember that…”, “Remember this…”, “Make a note…” or
“Add … to my list” already authorises that local addition. Kadence saves the item
and reports its number.

For a deletion, task completion, or another proposed stored change, Kadence reads
back what it would do and asks for confirmation. After the question finishes:

1. Start a new touch-initiated turn within 60 seconds.
2. Say “Yes” or “Yes please” to approve, or “No” to leave it unchanged.

A cancellation, disconnection or change of topic discards a pending confirmation.
If a write's outcome is uncertain, read the notes or list before repeating the
request; Kadence does not automatically retry such writes.

## 7. Configure the host

Set optional configuration in the same PowerShell session before starting the
application. For example:

```powershell
$env:KADENCE_TIMEZONE = 'Europe/London'
python -m kcore.appliance --visible-input
```

| Setting | Purpose / default |
|---|---|
| `--port` | USB control port; `COM4`. |
| `--baud` | Serial baud rate; `115200`. Keep the firmware's rate. |
| `--capture-ms` | Recording duration; `4800`, allowed range `2400`–`8000`. |
| `--reconnect-delay` | Seconds between reconnection attempts; `2`, must be positive. |
| `--visible-input` | Show credential input in the local terminal. |
| `--check` | Check dependencies and timezone without credentials or hardware access. |
| `KADENCE_WIFI_SSID` | Robot's Wi-Fi network; otherwise detected or prompted. |
| `KADENCE_WIFI_PASSWORD` | Optional process environment input; otherwise prompted. |
| `KADENCE_LAN_HOST` | PC's LAN IPv4 address reachable by the robot; normally automatic. Useful with Ethernet, VPNs or multiple adapters. |
| `KADENCE_TIMEZONE` | IANA timezone; `Europe/London`. |
| `KADENCE_DATA_DIR` | Override the local notes/tasks directory. |
| `OPENAI_API_KEY` | Optional process environment input for transcription. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Optional process environment input for reasoning. |
| `KADENCE_STT_MODEL` | Transcription model; current build default `gpt-transcribe`. |
| `KADENCE_THINKER_MODEL` | Reasoning model; current build default `gemini-3.5-flash-lite`. |
| `KADENCE_TTS_VOICE` | Spoken voice; `en-GB-SoniaNeural`. |
| `KADENCE_TTS_RATE` | Speech rate; `+0%`. |

Model names above document this build's configuration. An override must be
supported by its provider. The application does not save prompted credentials
to a settings file; environment values are managed by the terminal that supplies
them. Prompt entry avoids putting secret values in command history.

### Optional Home Assistant connection

Supply all three settings before startup:

| Setting | Value |
|---|---|
| `KADENCE_HA_URL` | Your Home Assistant base URL, such as `http://homeassistant.local:8123`, without an API path. |
| `KADENCE_HA_TOKEN` | Your locally supplied Home Assistant access token. |
| `KADENCE_HA_ENTITIES` | Comma-separated entity IDs, up to eight; for example `sensor.lab_temperature,light.desk`. |

Kadence reads the state and friendly name of those entities. Omit all three
settings if you do not use Home Assistant. Weather is available independently
and does not require an API key in this build.

## 8. Data, backups and service availability

On Windows, explicitly saved notes and tasks reside in:

```text
%LOCALAPPDATA%\Kadence\context.sqlite3
```

To back up or restore records, stop Kadence and copy the complete Kadence data
directory, or the directory selected by `KADENCE_DATA_DIR`. Treat this directory
as private: it contains the notes you chose to save.

Kadence does not automatically save recordings or conversation transcripts.
Normal speech processing sends audio to the transcription provider, request
context to the reasoning provider when needed, and reply text to the speech
service. Saved records can enter spoken conversation and subsequent session
context. Local storage does not make the complete voice interaction offline.

Some exact local requests can bypass the reasoning provider, but speaking to
Kadence still needs the transcription and speech services. If an optional tool
is unavailable, other capabilities can remain usable. Local presence and device
safety operate independently of those services.

## 9. Software maintenance

No reflash is needed to read this manual or obtain its documentation changes.
Keep using the approved installation. The accepted firmware remains tied to
source `9976548`; later documentation commits do not rename that firmware.

For a future approved release, use the source and firmware bundle supplied
together. The deployment script fetches the branch and requires the bundle's
full source commit to equal the updated checkout. It deliberately rejects an
older ZIP, including after a documentation-only branch update. Do not disable
that check or reuse an old bundle for a new deployment.

Stop the host, put the robot in download mode, and use the new release's exact
ZIP filename with:

```powershell
.\rebuild\tools\deploy.ps1 -Port COM4 -Bundle 'C:\path\to\the-matching-release.zip'
```

The supplied path must point to the new release file. Deployment checks the host,
verifies the manifest and flashes the specified images. For a source build of
an approved release, omit `-Bundle`; ESP-IDF 5.5.4 must be installed. `-BuildOnly`
performs preparation without flashing. `-HostOnly` maintains an already compatible
host installation without touching the firmware; it also fetches the branch, so
use it only when that branch's host is approved for the installed firmware.

After `KADENCE_FLASH PASS`, reset into normal boot if necessary and use the ordinary
startup command. Device calibration is preserved by the prescribed flash layout.

## 10. Release scope

All current operator capabilities are described above. The Windows dashboard,
top-strip animations, top-touch volume controls, scheduled reminders, camera
utilities and recognition features are proposed next-release work. They are not
controls available in this approved firmware. Factory StackChan documentation
describes additional features of M5Stack's firmware and is not a feature list for
the Kadence rebuild.
