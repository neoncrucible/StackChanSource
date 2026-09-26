# Live face training — host 0.4.10

The owner accepted 0.4.9 scene descriptions. Live face recognition and automatic
greetings still failed. This update addresses enrollment coverage and recognition
handling together. Firmware remains 0.21.6, SQLite remains schema 4, and the already
paired UnitV2 service needs no reinstall. Existing profiles/settings/photos remain.

## Install and train once

1. Quit Kadence including the tray instance. Extract the complete new download,
   run Install-Kadence.cmd and open the usual shortcut. Check version 0.4.10.
2. Start the server. In Vision → Profiles, select your existing profile and use
   REPLACE SAMPLES. Optionally enable Keep 3 local review photos first.
3. Follow Live training: face forward, turn a little toward either shoulder, turn
   the other way, lift/lower your chin, then lean nearer or farther at your normal
   seated position. Keep both eyes visible when turning. Four distinct samples
   are required for each view; the preview and prompts update throughout.
4. Wait for Saved: 20 samples. Cancel, poor frames or a timeout never replace a
   complete profile with partial training. The whole session is bounded to two
   minutes. Move slightly within a prompted view if it reports a duplicate sample.
5. Use LIVE RECOGNITION CHECK. Turn and try your normal distance while it collects
   up to 20 fresh frames. The result separates who is confirmed now from who was
   confirmed earlier in that check. Test images are temporary; it doesn't greet.
6. For greetings, enable Automatic Perception and Greetings in Perception, with
   the profile's Recognise and Greet switches on. Use TEST AUTOMATIC EVENT once,
   then leave/re-enter normally. Activity and Last greeting explain the outcome.

A previously attempted greeting is deliberately not repeated during an ongoing
visit; a persisted five-minute guard also applies. A recognition miss does not
consume the greeting. If the initial arrival look finds no identity, one follow-up
is queued within that occupied visit under the same rate limits.

## What changed

- Twenty varied live samples replace three nearly identical snapshots. Landmark
  ratios and face scale verify the requested coverage; a timer alone cannot count
  a new view. A fixed starting face plus nearest-sample agreement guards against
  mixing people. Additional faces, missed detection and poor quality pause sample
  acceptance while the session continues. Weak/small starting detections prompt
  repositioning. These are coarse coverage measures, not measured head angles.
- UnitV2 capture runs under one existing lease during training. Frames remain
  fresh and source-pinned; a source fallback cannot mix cameras partway through.
  Stop must succeed before enrollment commits. Voice and privacy interrupt work.
- Automatic recognition gets up to six frames, finishing early for clear repeated
  matches. Two of the last three associated observations must match one profile,
  including the current observation. Short missed detections can recover. Spatial
  continuity, conflicting identities and duplicate same-profile faces are checked.
  The old requirement that both images also have cosine similarity >=0.65 is gone.
- Identity threshold remains 0.55 with a 0.08 inter-person margin. Detector
  confidence is 0.8, while an enrollment starting view requires >=0.9 and at least
  64 pixels of face width. The recognition minimum remains 40 pixels. These are
  separate gates; a detected face does not establish identity.
- The blur filter uses contrast-normalized Laplacian variance, not an absolute
  threshold that rejected dim, enlarged face crops. Very smooth/flat crops still
  fail. Embedding alignment/model/encoding are unchanged and old profiles work.
- Accepted looks have terminal completion/cancellation/failure states. A voice
  interruption between frames no longer leaves health stuck on processing.
  Automatic work is bounded to 18 seconds; explicit live checks to 30 seconds.
- One automatic burst at most every 20 seconds; up to 18 reserved frames per
  rolling minute, early completion often uses fewer. AWARE heartbeat remains two
  minutes. Voice has priority and no automatic image goes to a cloud service.
- SQLite reads up to all 32 × 24 compatible samples. The old 96-row limit would
  have hidden later profiles with larger enrollment sets. Replacement is atomic.
  Three optional representative photos remain bounded below the desktop IPC cap.
- Exported recognition evidence contains counts, scores, margins and fixed reason
  codes. It excludes profile names/IDs, images, face embeddings and arbitrary text.

## Evidence and practical limits

Unit and integration checks exercise angle changes, brief detection gaps,
competing identities, duplicate candidates, profile switches, foreign faces,
quality failures, interrupted looks, one arrival retry, real SQLite persistence,
photo retention/deletion, cancellation and the voice/description regression.

The release also downloads hash-pinned OpenCV evaluation media into a temporary
build folder. The native YuNet/SFace pipeline is tested on a 770-frame tracking
video, using disjoint sampled frames for training and evaluation, plus two
other-person controls. On the local reference run, broader enrollment matched
16/16 held-out usable views; three frontal samples matched 14/16. Both other-person
controls were rejected. The same replay is required inside the Windows executable.
This small regression fixture is not an accuracy benchmark or evidence of results
on the owner's camera, appearance, room lighting or walking pace. It does not
simulate the full guided training interaction or prove demographic performance.

A saved embedding is a numerical face feature, not a photograph or a facial
percentage measurement. The factory UnitV2 service uses separate saved features;
Kadence does not import them. Its displayed match percentage cannot be equated
to a probability or directly compared to Kadence's cosine score. M5Stack explicitly
recommends slowly turning during its live training, which the earlier three-shot
Kadence flow did not support properly.

Primary references checked 26 September 2026:
- https://docs.m5stack.com/en/compute/unitv2/base_functions
- https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html
- https://github.com/opencv/opencv_extra/tree/4.13.0/testdata/cv/face
- https://github.com/opencv/opencv_extra/tree/4.13.0/testdata/cv/tracking/david

No physical UnitV2/robot was available here. Recognition and greeting acceptance
requires the owner's normal-use check. The accepted scene-description behavior
is preserved; this release does not claim to fix the separate firmware I2C fault.
