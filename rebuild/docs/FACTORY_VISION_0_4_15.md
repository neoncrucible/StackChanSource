# UnitV2 factory vision — host 0.4.15 / service 1.3.0

The Factory Vision tab exposes the verified algorithms shipped in the original
UnitV2 recovery image: Shape Detector, Color Tracker, Motion Tracker, Code
Detector, Object Recognition, Face Detector, Lane Line Tracker, Online
Classifier, Audio FFT and Shape Matching. They run on UnitV2’s own binaries;
Kadence does not reimplement or upload a competing model.

Every session uses the same single producer lease as Camera, Face Recognition
and Target Tracker. Stop, Privacy, voice activity, disconnect and the 30-second
UnitV2 lease expiry terminate the child process. Audio FFT is launched in its
own process group so its `arecord` child is released too.

Colour tracking uses the factory LAB thresholds and reports the selected colour’s
centroid/area. It is colour tracking, not a semantic claim that an object is
“red” or “blue”. Shape Detector recognises geometric contours. Shape Matching
and Online Classifier retain the factory requirement for their own onboard
training; Object Recognition requires the factory model files. These limits are
shown in the tab instead of being hidden behind a false “ready” state.

The host adds voice phrases such as “start shape recognition”, “enable colour
tracking”, “start object recognition”, “factory vision status” and “stop factory
vision”. The normal camera source, privacy and lifecycle checks still apply.

Setup remains reversible and does not flash firmware. Run SET UP UNITV2 once,
power-cycle the camera, pass TEST START / STOP, then select Factory Vision.
