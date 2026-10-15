# Kadence 0.6.0 — reactive companion candidate

This update addresses the owner's 15 October report: slow voice, camera setup
gates, lost tracking during conversation and a console that needed too many clicks.
It is a Windows host update. Keep CoreS3 firmware 0.21.6, the installed UnitV2
service and existing face profiles. SQLite remains schema 5.

## Everyday use

Tap Kadence, wait for the recording cue and speak normally:

- “What can you see?” / “What are you looking at?”
- “What colour is this?” / “Can you read this label for me?”
- “Track that” while gently moving one object in view.
- “Track something red” / “Follow this pen.”
- “Stop tracking” / “Turn camera privacy on.”

Camera questions and tracking start their own camera session. The background
awareness switch is separate; you do not need to enable it or manually run a
start/stop test before asking a question. The existing pairing is reused. A camera
that has never been paired still needs **Settings → Camera & awareness → Connect
UnitV2** once. Privacy always blocks acquisition.

Tracking uses local selection for one clear moving object or one unambiguous
colour region. Named objects use the configured Gemini vision service. If there
are several plausible targets, Kadence asks for a clearer view. Drawing a box
remains available as an optional manual control.

Ordinary conversation keeps the camera target and pauses head movement. A brief
occlusion can resume after three fresh, appearance-matched observations of the
same target within five seconds. Longer loss or a sudden jump requires a new
spoken request. No blind motor searching occurs.

If UnitV2 is mounted on the moving head, save the shared home in Motion and check
the mounting/directions once in **Tools → Tracking → Head setup**. Save head setup
moves to that home, checks the movement acknowledgement and remembers the setup.
Future spoken follow requests wait for speech to finish, position the head and
select from a fresh image. Changing the home invalidates the previous setup.
Without that physical setup, visual tracking still works and the head stays still.

The recognition greeting is now **“Alright, Boss. What's the plan?”** for the
profile whose saved greeting name is Boss; other profiles use their saved names.

## Response and camera changes

The earlier fast path is retained: the MP3 packet decoder feeds PC/Bluetooth
playback incrementally; it does not wait for the whole utterance to render. Two
single-use renderer processes now preload their native decoders while idle,
without sending text, using the network or opening an audio device. Private
sentence rendering overlaps model completion on every output route. Only a
validated matching reply is released. Cancellation reaps children and discards
unheard speech.

**PC / Bluetooth — fast streaming** is the Windows default. Changing the output
in Settings applies to the next reply without restarting. Existing saved output
choices are preserved. CoreS3 and Both retain the accepted complete-buffer audio
transport; this host update does not change the robot wire protocol.

The live target preview now transports UnitV2's JPEG directly instead of converting
every frame to PNG. The fixed 150 ms pause after each fresh frame is removed.
The camera already waits for a new observation, so the host does not need a second
polling delay. Preview acquisition also continues while a head movement waits for
its acknowledgement; there is still only one in-flight step and no motor queue.
The original 150 ms settling interval between head steps is preserved separately.
Activity diagnostics distinguish frame-request time, target-selection
time, first rendered PCM and first PC playback. Frame-request time includes waiting
for a fresh image and LAN transfer; it is not a sensor exposure measurement.

## Validation and limits

Regression coverage includes real child-process streaming and shutdown, native
decoder warm-up, invalid-plan speech discard, buffered-output overlap, real HTTP
camera ownership, automatic readiness, privacy revocation, native JPEG preview,
local-target ambiguity rejection, loss recovery, remembered head setup and
cancellation of a queued follow request. The Windows build additionally exercises
the frozen executable's warm speech handshake and incremental decoder.

Source tests and a Windows build cannot measure the owner's LAN, Bluetooth,
provider latency, native camera frame rate or physical servo response. This is a
candidate, not a new claim of consistent two-second replies or retail certification.
Do not replace the accepted 0.4.13 rollback or claim a hardware pass from CI.

Known scope: explicit tracking sessions remain bounded to 15 minutes; camera modes
share one producer and explicit snapshots switch away from tracking. This release
does not add always-listening wake words, locomotion, a working Stick microphone,
or fix the separate volume/top-swipe issue.
