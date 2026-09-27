# Object tracking — host 0.4.13 / UnitV2 service 1.2.0

This release adds a Tracking tab, native UnitV2 target tracking, voice target
selection and optional bounded head following. Face recognition/greetings retain
the physically accepted 0.4.12 implementation. Audio, scene descriptions, schema
5 and firmware 0.21.6 remain the baseline. No robot firmware flash is needed.

OpenClaw is parked. Colour/shape modes, object movement/removal alerts, event
descriptions and physical idle reflexes are separate follow-up releases. This
release does not promise that a tracked object is a pen, detect theft or identify
a person who moved it. The factory MOSSE tracker follows the selected image patch.

## Install and first visual check

1. Quit Kadence, extract the complete ZIP, run `Install-Kadence.cmd` and start the
   server from its shortcut.
2. Vision → Camera → **SET UP UNITV2** installs service **1.2.0**. Power-cycle the
   UnitV2, select **ON DEMAND**, then run **TEST START / STOP**. Existing native
   profiles, pairing key and factory service backup are preserved. Do not flash
   the recovery image. Service 1.1.0 still supports accepted face functions but
   cannot run the new target tracker.
3. Select UnitV2 or AUTO, with Privacy off. Open **Vision → Tracking → OPEN
   PREVIEW**. Hold one distinctive object still. Drag a tight rectangle around
   it, including a little surrounding detail. This selection is entirely local.
4. Move it slowly. The green box should follow it. Head movement is off until
   you arm it. A vanished target immediately stops further head steps; after
   1.5 seconds without a result, LOST requires explicit selection again. Large
   jumps also stop following instead of guessing where the object went.

You may instead enter **this pen** and choose **FIND & TRACK**, or say
**Kadence, follow this pen** during a normal voice turn. One requested image goes
to the configured Gemini image service for initial object location. The selected
patch is checked against a current frame before native initialisation. Hold it
still until selection completes. Ambiguous, textureless, tiny or changed targets
are rejected with a useful message; manual drawing remains available without a
Gemini key. Continuous tracking runs locally on UnitV2, not through an LLM.

## Optional head following

The UnitV2 must move with the head. A fixed camera on the desk can track on
screen, but must not drive this head-relative controller.

1. Check the mounting/cable-space box. Choose a comfortable home pose using
   the displayed yaw/pitch values. **MOVE HOME & ARM physically moves the head**
   to those values, verifies the existing firmware's acknowledgement and torque
   release, then enables following for this server session.
2. Open preview and select a target again, or ask **follow this pen**. Hold it
   still while Kadence selects it and finishes speaking. Three fresh stable
   observations are required before head steps start.
3. Move the target gently left/right, then up/down. If an axis moves away from
   it, choose **STOP / DISARM**, change the corresponding Reverse switch, then
   Move Home & Arm and select again. Mount orientation is not guessed.
4. **STOP / DISARM** or **stop tracking** ends the camera session and disables
   further following. **RETURN HOME** is a separate deliberate movement, available
   while armed. There is no automatic return-home movement after a voice turn.

Following uses at most 2° per command, within ±18° yaw and ±15° pitch of the
chosen home, and within the existing firmware envelope. Only one pose command
is in flight; it must acknowledge execution and torque release before another
can be issued. Stop/Privacy/voice prevent new steps. An already-issued bounded
step settles first; the existing firmware has no instantaneous tracking-stop
command. A failed acknowledgement disarms following. The response is stepped,
not a high-speed pan/tilt gimbal. No servo zero/calibration is rewritten.

## Camera and voice ownership

- Tracking owns the single camera producer while active. Automatic face looks
  wait; their saved settings and profiles are retained. They become eligible
  again after tracking releases the camera.
- Another camera action, Privacy, a new voice turn, robot disconnect or server
  shutdown ends the tracking session. Ask to follow again to acquire a fresh
  target. A following request issued during voice can select the object, but
  motor steps wait until speech is complete.
- Manual arming is not restored after a server restart or disconnect. Privacy
  and Stop/Disarm also clear it. It cannot be enabled by a model proposal.
- Sessions last up to 15 minutes. UnitV2 independently expires its camera lease
  after 30 seconds without the host. Images and target patches are temporary;
  neither frames nor object labels are added to the recognition database.
- Existing voice activation remains unchanged: use the normal tap/listening
  flow. This release does not add a wake-word detector.

## Evidence and acceptance

Factory `bin/target_tracker` SHA-256:
`0cec301c02f8ab75bccedeedafef38758f3bf1ff931624683609b3cf315ed112`.

The original recovery archive was checksum-verified and extracted for inspection,
never flashed. The original tracker accepts a 640×480-coordinate ROI, processes
320×240 images with MOSSE and emits coordinates before each successful image.
It does **not** emit a reliable lost event. The bridge associates coordinates
with exactly one image and clears them when the next image has no coordinates.

Primary references:
- https://docs.m5stack.com/en/compute/unitv2/base_functions
- https://github.com/m5stack/UnitV2Framework/blob/68506ea70b3a00ecc1719cb36c2a607c6a7b3062/main/target_tracker.cpp
- Original recovered `bin/target_tracker`, framework protocol and web control.

Automated checks cover process/HTTP integration, stale boxes, invalid regions,
lease expiry, selection cancellation, camera ownership/privacy, bounded motor
requests, delayed acknowledgements, voice authorization and preview coordinates.
They cannot establish physical motor direction, smoothness, target retention on
your particular pen or live Gemini localisation accuracy. First accept on-screen
tracking, then the small left/right/up/down head check above. Keep accepted host
0.4.12 available until this hardware check passes.
