# Camera and perception — host 0.4.13

The new Tracking tab is documented in OBJECT-TRACKING.txt. It uses camera service
1.2.0 and retains the physically accepted 0.4.12 native face/greeting baseline.

Audio in 0.4.11 and scene descriptions are accepted by the owner. This update
changes UnitV2 recognition and enrollment; firmware stays at 0.21.6, with no flash.

## Install once, then use the saved onboard profiles

1. Quit Kadence, extract the complete ZIP and run `Install-Kadence.cmd`.
2. In **Vision → Camera**, confirm the UnitV2 address and select **SET UP UNITV2**.
   Install the updated service, then unplug/reconnect **UnitV2 power**. This is
   required even if start/stop already worked on service 1.0.0. The installer
   preserves native face files, the pairing key and the original service backup.
   SSH user is `m5stack`; its factory password is `12345678` unless changed.
3. Start Kadence. Select **ON DEMAND**, leave Privacy off and pass
   **TEST START / STOP**. Service verification is tied to the installed service version.
4. **Profiles → REFRESH FROM UNITV2** loads the profiles already saved there.
   Existing native profiles need no PC enrollment. Check each profile's
   **Recognise** and **Greet** switches and save preferences as needed.
5. To add or improve a profile, choose **OPEN UNITV2 TRAINING**. In the browser,
   select a profile or Add one, enter its name, click **train**, move gently
   through comfortable everyday angles, then **stop** and **SAVE ON UNITV2**.
   Wait for **saved and verified**, then **FINISH & RETURN TO KADENCE**.
   There is no 20-sample target, forced chin-up pose or 120-second enrollment
   deadline. The UnitV2's own native training status is displayed live.
6. Run **LIVE RECOGNITION CHECK**. It uses native UnitV2 results, shows its match
   scores and distinguishes a current confirmation from one seen earlier.
7. For greetings, choose **EVENT ONLY**, enable **Automatic Perception** and
   **Greetings**, and use **TEST AUTOMATIC EVENT** once. Activity reports the
   completed look and greeting outcome. A continuous visit is not greeted again;
   tests also honor the five-minute per-person greeting guard.

The focused browser page runs the original factory face-control JavaScript and
original `bin/face_recognition` executable. It does not restart the unrestricted
factory server or a second camera producer. Other factory function/firmware,
Wi-Fi, reset and upload controls are not exposed by this training session.

## What is saved

The factory engine saves `data/face_recognition_info.json` (names) and
`data/face_recognition_features.dat` (128 floating-point features per profile).
Those files remain on UnitV2 and are authoritative. They contain no photo gallery.
The live browser image and native preview are temporary. Existing PC review
photos remain reviewable with their legacy profiles, but UnitV2 matching no
longer uses the PC SFace database. Selecting the robot camera explicitly retains
legacy PC recognition; use UnitV2 or AUTO for onboard identities.

SQLite schema 5 stores native device/name links, display/greeting preferences,
visits and outcomes, without importing UnitV2 feature vectors. Refresh uses the
current device catalog; recognition refreshes it before each burst and rejects a
changed catalog during the burst. A missing or disabled native profile cannot
be confirmed. Old metadata and preferences survive device/profile absence.
Renaming a Kadence display/greeting name does not rename the native face.

**BACK UP DATABASE** covers PC metadata, not onboard features. Before native
training changes, the bridge keeps a verified copy of the previous onboard pair
under `payload/kadence-native-backups/`. These backups remain on UnitV2. A save
journal allows rollback after interrupted factory writes; a successful Save
requires validated names, feature length/content and flushed files. Startup
recovers an interrupted save before starting any camera producer. Restore of the
original service does not delete profiles or these backups. Disabling Recognise
or Greet does not erase a native profile; PC Delete cannot pretend to erase it.

## Ownership and interpretation

- One native or plain camera producer owns a 30-second lease. Browser access
  needs a short-lived ticket issued by the paired Kadence host. Browser activity
  cannot renew host permission. Closing the browser, closing Kadence, Privacy,
  Stop or starting voice work ends the training session. Save before leaving.
  Disconnect expiry discards unsaved in-memory training, retaining saved files.
- Recognition uses the factory `match_prob` threshold above 0.5, plus two
  agreeing fresh observations. These are native similarity scores, not calibrated
  certainty percentages and not SFace cosine scores. Duplicate identity claims
  are withheld. The factory's `render:0` disappearance event clears old matches.
- No cloud face recognition is involved. Scene descriptions still use the
  accepted Gemini path. Voice transport, firewall setup and firmware are retained.
- The focused page follows the factory engine's training behavior. Keep only
  one person in view; the factory learns its largest detected face. The bridge
  rejects starting training when its latest result already contains a group.
- The camera is stopped before ordinary on-demand greeting delivery. Keep Ready
  is an explicit choice to retain a producer; switching between plain capture and
  native recognition stops the previous owned child before launching the next.

## Evidence and physical acceptance

Verified factory recovery archive SHA-256:
`c36022a56f101608625571115a9c0165f9a203151b58f69e1379ee53483f88da`.
Original native executable SHA-256:
`00012bd3cda05f4fc482542830822f9bb15fe3c1a23794a106edf206ec13fd99`.

Primary protocol and persistence references:
- https://docs.m5stack.com/en/compute/unitv2/base_functions
- https://github.com/m5stack/UnitV2Framework/blob/68506ea70b3a00ecc1719cb36c2a607c6a7b3062/main/face_recognition.cpp
- Original recovery package `server_core.py`, factory `face_recognition.js` and
  `post.server.js`, inspected directly without flashing a device.

Automated tests use real subprocesses, HTTP, native protocol fixtures, database
migration and the actual greeting scheduler. They prove integration, lifecycle,
save recovery and cancellation behavior; they do not measure accuracy on the
owner's face.

**Physically accepted by the owner on 27 September 2026 at 21:28 BST.** All tests
were reported passed, native recognition scores improved after training, and
greetings worked well. Supplied screenshots confirm current native recognition,
an 85.7% native similarity score and a completed perception burst with greeting
delivered. Host 0.4.12 is the accepted native recognition/greeting baseline.
The manual stop/start step is accepted as minor workflow polish for later.
The evidence does not establish which physical sensor triggered the greeting;
that is separate from the facial recognition sign-off.
