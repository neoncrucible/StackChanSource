# Camera states and local perception — host 0.4.5

Branch: `kadence/functionality`. Firmware stays at 0.21.6; **no flash**.
The owner accepted the 0.4.0 physical baseline on 25 September 2026.
The owner accepted 0.4.3 voice responsiveness; its voice pipeline is retained.
Host 0.4.4 supplies UnitV2 producer lifecycle control. Host 0.4.5 connects the
existing sensor salience layer to bounded local perception. Firmware and schema
v4 are unchanged. Both releases still need their new physical acceptance checks.
0.4.4 is the lifecycle-only checkpoint; 0.4.3 is the accepted voice rollback.

## Console and daily use

Install this desktop update with its `Install-Kadence.cmd`, then open the normal
Kadence shortcut. Start the server. Open **Vision**.

Automatic perception defaults **disabled**, including when an older EVENT_ONLY
or AWARE preference exists. First complete UNITV2-START-STOP.txt. The successful
two-cycle test saves a proof tied to this camera pairing and service version.
Then select EVENT ONLY, check **Enable automatic perception**, and Apply & Save.
The console displays both the active gate and each accepted/deferred/suppressed
decision. No PowerShell is needed for daily operation.

- **OFF**: automatic capture disabled; deliberate Capture and voice “look” work.
- **EVENT ONLY**: a debounced arrival, deliberate gesture or abrupt close approach
  can request a pair of frames. Established desk movement and cached sensor
  packets do not repeatedly trigger recognition. There is no timer capture.
- **AWARE**: Event Only plus one pair at most every 120 seconds while the zone is
  occupied. This is sparse evidence, not continuous video surveillance.
- **PRIVACY**: blocks every Kadence camera consumer, cancels pending acquisition,
  clears the manual preview and prevents description/save of that preview.
  Already-started external requests cannot be unsent. An explicit save whose
  file/database transaction has started is allowed to settle consistently.

Select a policy, source and optional actions, then **Apply & Save**. Privacy applies
immediately when clicked. Policies persist across server/application restarts.
The first installation defaults to OFF. A damaged policy file fails closed into
privacy. Settings are in `camera-settings.json` in the normal Kadence data folder.

**AUTO** tries UnitV2 first and the available StackChan camera second. Frame
provenance always records the camera actually used. An explicit source does not
silently switch. The UnitV2 address defaults to the owner's last verified address,
192.168.40.175; it remains editable because DHCP may change it.

Camera status shows IDLE, STARTING, CAPTURING, FAULT or PRIVACY. Local analysis
shows separately as processing/ready/unavailable. ToF zone state and sensor health
are separate from face evidence. The console never calls a ToF target a person.
Successful automatic frames are not displayed, uploaded or saved. Manual capture
continues to show its preview; Gemini receives only explicitly requested object
questions and images, never autonomous identity work.

## Local enrollment and recognition

The complete executable includes pinned OpenCV YuNet/SFace models. No model or
face-image download occurs at runtime. Enrollment is explicit:

1. Set the intended source/address and stand alone, facing it in good light.
2. Enter a name, then **Enroll 3 Samples**. Keep your face clearly visible.
3. The operation checks three independent frames for one usable, consistent face.
   Only normalized 128-dimensional local embeddings are persisted. No enrollment
   photographs are retained. This is not an authentication mechanism.
4. Refresh lists local profiles. Remove Profile deletes its embeddings and
   anonymizes its name while retaining anonymous session/action history.

Local recognition uses cosine >=0.55 and a >=0.08 lead over other people, then
requires agreement across two frames with >=0.65 inter-frame similarity.
Ambiguous matches stay unconfirmed. These conservative defaults require physical
validation with this camera placement; they are not a measured accuracy claim.
Small (<40 px) or severely blurred faces are excluded. Up to eight faces are
processed per frame; enrollment is capped at 32 people with three samples each.

**Greet confirmed people once per visit** is optional and initially off. It uses
an explicit fixed greeting and the selected speech output; it does not move the
head or invoke model tools. **Local notice for an unenrolled face** is also off
by default and displays a Windows console/tray notice, not an identity claim.
Names used in an enabled spoken greeting may pass through the existing speech
provider; embeddings and autonomous images never leave local recognition.

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
