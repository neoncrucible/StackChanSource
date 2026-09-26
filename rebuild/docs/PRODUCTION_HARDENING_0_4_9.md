# Host 0.4.9 — descriptions and voice recovery

This is a complete Windows host update for the existing 0.21.6 robot firmware
and paired UnitV2 service. Install the whole package with `Install-Kadence.cmd`.
No firmware flash, camera service reinstall, profile replacement or SQL migration
is required. Existing profiles, optional reference photos, keys and settings stay
in the existing data directory. Voice output selection and head alignment remain
under their existing owners.

## What the latest evidence establishes

The owner's 26 September screenshots show a usable face, a successful local
identity match and a delivered automatic greeting on 0.4.8. The latest diagnostics
show a `tcp-connect` failure, code 116, before recording. Restarting the server was
followed by completed voice turns. Both subsequent voice looks acquired and
released a UnitV2 frame, but returned no scene description.

The description adapter still read the removed `outputs` schema. Google's current
Interactions REST response places text in `steps`, inside `model_output.content`.
The previous code discards that valid text. The new tests reproduce this with the
official response structure. The owner's export did not contain the provider
body, so it cannot establish the exact HTTP response for each individual look.

Reference: https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026

## Changes

- Parse complete model output from the current API structure. Ignore echoed
  input, reasoning summaries and tool output. Keep explicit requests stateless
  (`store: false`) and pin the documented response revision.
- Return specific spoken and visible results for credentials, quota, model,
  timeout, malformed/empty/incomplete response and service failure. Never expose
  provider response bodies, API keys or HTTP request contents in diagnostics.
- Enforce a 20-second total description deadline, including any slow response
  body. Retry only one transient 502/503/504 response, within that deadline.
  A complete spoken camera look has its own 26-second deadline inside the existing
  tool boundary. Cancelling or enabling privacy invalidates the in-flight result.
- Add **Look & Describe** in Vision → Camera. The actual snapshot and its returned
  description appear side by side, with source, capture time and explicit status.
  The main action and result are visible at the minimum 980×690 window size.
  Selection and UnitV2 setup controls follow below. Capture Only and Describe
  Snapshot remain available. A new look clears the old preview first.
- Bound voice connection to 30 seconds, allow recording duration plus eight
  seconds for upload, preserve the existing 52-second provider deadline, and wait
  for playback proof only for the audio duration plus ten seconds. A provider
  failure releases a missing final device ACK immediately. An unknown outcome is
  never added to completed conversation history.
- After a failed LAN connection, stalled device stage or unconfirmed cancellation,
  ask the existing supervisor to reopen the robot connection. This can reboot the
  robot through USB, as a server restart does. Do not retry the microphone or
  replay a question. Allow at most one such recovery per two minutes; persistent
  failures instead show LAN/Windows Firewall guidance. Reconnected means the
  serial session is ready; the next voice turn still tests audio end to end.
- Refresh an auto-detected PC address before each voice attempt. Preserve an
  explicitly selected address. Display the active audio endpoint in Overview.
- Distinguish ambient Attentive presence from **Connecting Audio**. Device polls
  cannot overwrite an active transcription, reasoning, camera or speech phase.
  Overview includes cancellation and the last voice/recovery result.
- Release audio connection ownership before cancellable cleanup. The new
  interruption tests exposed that old cleanup could strand closed connections.
  Track cancelled SQLite jobs until their own worker closes its connection, so
  shutdown cannot abandon an in-progress database transaction.
- Coalesce repeated device/producer polling, retain transitions, and export a
  separate bounded `important_events` journal for voice, description and failure
  evidence. Neither journal includes images, names, embeddings or conversation.

## Release gates

The checked-in tests run the normal companion, tool boundary, camera-frame
handoff, HTTP adapter, speech synthesis boundary, real loopback audio transport,
SQLite and acknowledgement lifecycle. Hardware and external API responses are
substituted with controlled fixtures; they do not prove live account access.

Specific cases cover the modern API structure reaching the exact spoken reply,
quota/auth errors, a bounded transient retry, slow trickle/oversize responses,
privacy and touch cancellation during description, a successful next look,
missing connection and playback ACKs, provider failure with a missing device
ACK, supervisor reconnect without replay, cooldown, explicit/auto LAN settings,
database settlement and retention of useful diagnostics after 500 device polls.

Windows CI additionally checks the normal ownership/alignment gate and the
packaged executable: modern vision response parsing, speech decoding, Windows
local speech, verified local face models, profiles and photo review/deletion,
backup, private IPC and clean exit. Live Gemini access, physical Wi-Fi, robot
microphone/speaker and Windows/Bluetooth acoustic output require hardware use.

## Short device acceptance

1. Quit the old tray instance, install 0.4.9, start the server and use the existing
   saved camera/profile settings. No re-enrollment is needed.
2. Ask “What can you see?” with an ordinary object in view. Vision → Camera must
   show that fresh image, its source/time, and the same description she speaks.
   **Look & Describe** exercises capture and description directly from the PC.
3. Ask two ordinary questions. Cancel one further look by touch, then ask a new
   question. There must be no stale reply and no need to restart the app.

If live access fails, the console now distinguishes capture from description and
shows the specific provider/connection outcome. Export Diagnostics after the
failure; important events are retained separately from polling.

## Remaining physical limit

The earlier 0.21.6 CPU0 I2C receive-interrupt crash is documented in
`FIRMWARE_CRASH_2026-09-26.md`. This host release improves recovery, not the I2C
driver. The latest supplied logs contain a LAN connection failure rather than
another captured instance of that panic. Firmware is deliberately not changed on
an unverified driver-race hypothesis. A software release pass does not constitute
production acceptance of the complete physical robot.
