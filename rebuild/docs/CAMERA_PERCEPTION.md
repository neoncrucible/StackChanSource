# Vision console, profiles and voice — host 0.4.7

Branch: `kadence/functionality`. Firmware stays at **0.21.6**; **no flash**.
The accepted 0.4.3 voice transport/output pipeline and head alignment are retained.
0.4.7 includes the 0.4.6 UnitV2 setup repair and the existing lifecycle service.
The owner has reported start/stop and Privacy working. Recognition, greetings,
voice camera commands and this new console still need physical acceptance.

## Start here

Install using `Install-Kadence.cmd`, open the normal shortcut and check the console
shows **0.4.7**. Start the server and select **Vision**. It now has four tabs:

- **Camera**: choose UnitV2, StackChan or AUTO; Apply and Save. Capture checks the
  actual view. Setup, start/stop test, mode and confirmed producer state are here.
- **Perception**: a prominent **Enable Automatic Perception** switch, actual gate,
  last completed look, recognition result and greeting outcome. Enabling from OFF
  selects EVENT ONLY. The enable, greeting and notice switches save immediately.
- **Profiles**: the real saved names, compatible/total sample counts, recognition
  and greeting eligibility, and sample dates. Enrollment progress stays here.
  Rename, disable recognition/greeting for one profile, replace samples or delete.
- **Activity**: live sensor proposals, accepted/deferred/suppressed decisions,
  recognition/greeting results and producer stop confirmation. Refresh History
  reads recent saved event/action metadata, including previous sessions.

Camera source/address apply to manual capture, voice looks, enrollment and local
perception. After editing source/address, use **Apply and Save**. Capture, enrollment
and test buttons also apply the displayed camera settings before starting.

A previously installed working UnitV2 service does not need reinstalling for this
host update. If the console requests a lifecycle test, use **Test Start / Stop**
with automatic perception off. A successful two-cycle test saves proof tied to the
pairing and service version. No daily PowerShell commands are needed.

## Enroll, inspect and test a profile

1. In Camera, select UnitV2 and Capture to check framing and lighting.
2. In Profiles, inspect the saved list first: an earlier successful enrollment
   appears with **3 / 3 compatible** samples. Enter a new name only for a new person.
3. Face the selected camera alone and click **Enroll 3 Samples**. Each accepted
   sample advances the progress bar. Success says **Saved: name** and refreshes
   the list. A failure remains beside the enrollment controls.
4. Click **Test Recognition**. It takes two fresh frames for local matching,
   works with automatic perception off, and never creates a visit or greeting.
   Privacy still blocks it. It names someone only when both frames agree.
5. Restart Kadence and reopen Profiles to verify persistence. Saved rows are read
   from the same database, not an in-memory list.

Select a saved row to rename it or change its Recognise/Greet switches, then
**Save Profile**. **Replace Samples** keeps the same person ID and eligibility;
old samples stay saved until all three replacements validate and commit together.
**Delete** removes current biometric samples and anonymizes the name/history.
Existing database backups retain their copies.

Enrollment stores a name and three normalized 128-dimensional embeddings, not
photographs. The packaged YuNet/SFace models perform recognition on this PC.
Factory UnitV2 face-tracking identities are separate and are not automatically
imported. This is local presence recognition, not an authentication mechanism.

The existing **SQLite schema v4** is reused; no SQL server setup or migration is
needed. The default database is `%LOCALAPPDATA%\Kadence\database\kadence.sqlite3`
(`KADENCE_DATA_DIR` can override the root). The exact path is shown in Profiles.
**Back Up Database** creates an integrity-checked SQLite snapshot in the adjacent
`backups` folder and reports its full filename. It includes committed WAL data,
profiles, reminders and projects; it is a database backup, not a media/settings
archive. No automatic photos are added to the database.

## Test automatic perception and greetings

1. In Perception, enable Automatic Perception. The gate must report enabled;
   otherwise it explains Privacy, stopped mode or a missing lifecycle test.
2. Choose EVENT ONLY for arrivals/gestures/close approaches, or AWARE to add
   occasional occupied-space checks. The mode selection saves immediately.
3. Enable greetings if wanted. The profile's individual **Greet** switch must
   also be on. Enabling greetings alone never enables automatic capture.
4. Click **Test Automatic Event**. This submits one deliberate gesture proposal
   through the real gates, frame budget, two-frame matcher and greeting dispatch.
   It can greet if eligible; it never bypasses Privacy or the once-per-visit and
   five-minute greeting guards. Wait at least 20 seconds between burst tests.
5. Read Last Look, the greeting result and Activity. A completed recognition test
   is separate from a delivered greeting. Failed/unavailable speech is not claimed
   delivered. Then verify a real arrival by leaving until CLEAR and returning.

Ordinary desk movement is suppressed. EVENT ONLY has no timer. AWARE adds at most
one two-frame check every 120 seconds while occupied. No automatic frames go to
Gemini or disk. Names in optional spoken greetings may pass to the existing speech
provider. Normal voice work interrupts background perception and enrollment.

## Voice commands

These common phrases run directly without waiting for a reasoning-model tool choice:

| Say | Actual action |
| --- | --- |
| What can you see? / What am I holding? / Read this | Take a fresh selected-camera snapshot and describe it with Gemini. |
| Camera status / Which camera are you using? / Are you looking? | Report saved source, privacy, producer state, automatic gate and last local result. This is not a fresh image. |
| Use the extra camera / Use the Unit V2 camera | Save explicit UnitV2 selection. |
| Use the robot camera | Save built-in StackChan selection. |
| Enable / disable automatic perception | Save opt-in; enabling from OFF chooses EVENT ONLY. Lifecycle checks still apply. |
| Enable / disable greetings | Save greeting preference; tell you if automatic perception is still off. |
| Turn privacy on / off | Save the same privacy control used by the console. |
| Stop the camera / Start the camera | Select UnitV2 STOPPED / ON DEMAND mode. Start means ready for a requested capture. |
| Keep the camera ready | Select UnitV2 KEEP READY with its renewable lease. |
| Use aware mode / Use event only mode | Enable perception in that mode, subject to lifecycle checks. |

A Gemini key is required for picture descriptions even when Ollama supplies ordinary
conversation. Missing keys and Privacy produce explicit spoken explanations.
Object descriptions do not identify people; profile enrollment/management remains
in the console. Model-proposed setting changes still require a concrete spoken
confirmation; the model cannot grant itself authorization. All paths share the same
CameraManager and the existing in-turn robot capture channel, with no second serial
owner. Failed operations are not silently retried.

## Privacy and recognition limits

OFF disables automatic capture while retaining deliberate capture/look/tests.
Privacy blocks every Kadence camera consumer, invalidates pending frames, clears
preview and requests a producer stop. Check **stop confirmed**; software privacy
is not electrical power-off. An already-started external request cannot be unsent.
An explicit database/file transaction already started settles consistently.

AUTO tries UnitV2 then the available StackChan camera. Explicit camera selection
never silently switches. Status/results show the actual source when known.
An invalid saved settings file fails closed into Privacy. Settings persist in
`camera-settings.json` in the normal Kadence data folder.

Recognition requires cosine >=0.55, a >=0.08 lead over other people and agreement
across two frames with >=0.65 inter-frame similarity. Ambiguous matches remain
unconfirmed. Small (<40 px) or severely blurred faces are rejected. Up to eight
faces are processed per frame; enrollment is capped at 32 people with three samples.
These thresholds still require testing with the actual camera placement and light.

## Runtime contracts and limits

ReflexController still only proposes events and cannot access cameras, servos,
speech or an LLM. PerceptionController independently enforces the explicit opt-in,
camera policy, privacy, enrollment exclusion, lifecycle proof, voice priority
and capture budget. CameraManager enforces those acquisition boundaries again.
An unpaired UnitV2 can never be accessed automatically through the legacy API.

One CameraManager owns acquisition for manual, voice, enrollment and automatic
requests. Explicit requests preempt automatic work; one explicit waiter is
allowed, and other concurrent requests fail busy rather than building a queue.
Privacy/configuration changes invalidate generations. Bounded blocking network
workers retain ownership until they settle; cancelled frames never publish.
The in-turn StackChan callback is preserved to avoid taking its serial owner twice.
UnitV2 bootstrap and first-frame reads share bounded deadlines. Camera failures
back off for 15 seconds. Automatic requests reserve two frames, with a 20-second
minimum interval and at most six automatic frames per rolling minute.
One UnitV2 lease covers each pair and is released before any optional greeting.
Enrollment similarly holds one lease for its three explicit samples. OpenCV
uses one CPU thread so background perception leaves headroom for voice.

A busy voice turn may defer one arrival for at most 15 seconds, or a gesture /
close approach for 5 seconds. Repeated input cannot extend that deadline. An
arrival may wait briefly for the capture budget. Departure, privacy, settings
changes and explicit interruption clear pending work. There is no event backlog.

ToF enters the zone at <=900 mm with 2 seconds of distinct valid evidence, leaves
at >=1200 mm with 4 seconds of evidence, and holds its prior decision between
thresholds. Stale/invalid/missing samples are UNKNOWN, never an invented CLEAR.
Serial access uses the existing host, not another COM4 process. Startup and known
sensor discovery pauses can briefly report UNKNOWN. These desk distances are
initial calibration defaults, not claims about the actual installation geometry.

Individual visual evidence expires after 180 seconds, independently of ToF.
Known identities are matched again on each evidence pair; unchanged face count
cannot renew identity. Unknown continuity is limited to closely spaced visual
matches, never a global UNKNOWN identity. Sparse observations can miss a person
replacement; EVENT ONLY intentionally cannot guarantee detection of every change.
AWARE provides occasional rechecks. Visual sessions are closed on zone clear,
privacy/policy changes, device reconnect, stop, or expiry; end timestamps use last
visual evidence. A long host scheduling gap reconciles sessions as a resume.

Schema v4 is reused. Meaningful occupancy, identity, capture decisions and one
summary per completed two-frame analysis are recorded; raw sensor samples and
image bytes are not logged. Action intent and claim are transactional; each
session/kind is unique. Greetings already attempted in an ongoing occupancy
visit are suppressed even if its visual evidence later expires. Ambiguous
matches are never announced as unenrolled people.
Eligibility and a 20-second expiry are checked before delivery. Recent greetings
for the same profile / unknown notices are suppressed for five minutes across
sessions and restarts. Interrupted delivery becomes uncertain and is not replayed.
Recognition never authorizes a command or opens a URL. No autonomous images are
written, so there are no automatic files needing a retention sweep. Existing
manual saved observations remain pinned and unchanged.

## UnitV2 hardware capability boundary

The verified factory path bootstraps `/`, selects Camera Stream via `/func`, then
reads one JPEG from `/video_feed`. Closing HTTP stops Kadence's retrieval, **not
necessarily the producer or sensor**. The factory browser's stopLoadStream only
stops browser polling, and the framework stream flag is not evidence of sensor
standby. Host 0.4.4 adds the separate, reversible UnitV2 lifecycle service;
see UNITV2-START-STOP.txt. It owns the verified vendor camera process, confirms
process exit, and expires unattended leases on the camera. Legacy manual
capture remains available before that service is installed. Electrical sensor
standby, power reduction and cooling remain unmeasured; physical power-off
still requires disconnecting UnitV2 power.

## Current acceptance pass

1. With automatic perception unchecked and policy OFF, complete UnitV2 setup
   and TEST START / STOP. Confirm the two images and STOPPED / stop confirmed.
2. Check the live ToF / gesture proposals while moving normally at the desk.
   Ordinary motion should increase Background without repeated arrival events.
3. Enroll one face explicitly. Enable automatic perception with EVENT ONLY and
   leave optional greetings/notices unchecked for the first pass.
4. Leave the ToF zone until CLEAR, then return. Expect one accepted arrival,
   two-frame analysis and a completed burst. The producer should stop afterward.
   Move normally: no repeated capture. After 20 seconds, make a deliberate
   gesture; expect another bounded burst. A sudden close approach also qualifies.
5. Turn Privacy on during a request. No new image or identity may publish; the
   producer must report stopped or honestly report stop unconfirmed. Disable
   Privacy and verify an ordinary voice answer and unchanged head alignment.
6. Enable the optional greeting, leave and return, and confirm one greeting for
   the visit. Normal desk movement must not repeat it. Recognition thresholds
   still need validation with the physical placement and lighting.
7. Finally select AWARE while occupied. Expect at most one extra pair after
   120 seconds without another accepted event. EVENT ONLY has no heartbeat.
   Stop/quit/reopen and verify the saved policy, privacy and opt-in settings.

Diagnostics export includes sanitized lifecycle status and up to 120 perception
decisions, separate from the bounded sensor proposal log. It excludes names,
embeddings, images, pairing keys and transcripts. The new physical pass is not
signed off by automated tests. Bounded servo reflexes, semantic object novelty,
automatic LLM cognition, tools/OpenClaw and further latency tuning are subsequent
work; this release provides the local presence and identity layer.

## Model provenance

OpenCV Zoo pinned commit `47534e27c9851bb1128ccc0102f1145e27f23f98`:
https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98

YuNet 2023mar: 232589 bytes, SHA256
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` (MIT).
SFace 2021dec: 38696353 bytes, SHA256
`0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` (Apache 2.0).
Licenses ship in ThirdParty/OpenCV-Zoo. Source deployments may explicitly run
`tools/prepare_face_models.py <Kadence-data-folder>/models/faces`; otherwise missing
models disable local recognition with visible status. Manual camera use still works.
