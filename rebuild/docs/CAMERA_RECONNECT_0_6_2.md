# Kadence 0.6.2 — keep camera setup, recover the connection

This is a desktop-only repair for the repeated generic “camera unavailable”
message and the misleading Connect UnitV2 button. Install-Kadence.cmd retains
the existing application data and pairing. No CoreS3 flash, UnitV2 reinstall,
face training or settings reset is needed.

- Reconnect camera uses the existing authenticated service. It stops the
  requested session, proves one fresh image and a confirmed capture stop, and
  reports the real result. It never launches SSH or changes pairing.
- A camera that boots after the app is retried automatically, with bounded
  requests and increasing delays. Privacy, OFF, shutdown and address changes
  revoke the old attempt. Voice startup is not blocked by background retries.
- Explicit camera questions can be retried immediately. The 15-second backoff
  still limits automatic capture attempts, and failures are scoped by address.
- An expired session owned by this host is stopped and renewed once. Recovery
  cannot stop a different owner's session. Authentication nonce expiry gets
  one fresh challenge within the existing request deadline, not a setup prompt.
- Home and Diagnostics distinguish unreachable camera, service unavailable,
  rejected pairing, missing service, image timeout, unreadable image and process
  conflicts. Raw responses, keys and image bytes are excluded from diagnostics.
  A cleanup error no longer overwrites the original image-capture failure.
- Setup saves the address to the same persistent camera settings used at app
  startup. Its default checks an existing pairing without SSH or a password;
  install/repair is explicit. A successful new service installation still needs
  a single camera restart. Subsequent desktop updates do not.

The host repairs and regression tests do not identify the exact network or
camera-service failure on the owner's UnitV2. No owner hardware was reachable
from the build environment. If capture still fails, the new Home message is
the useful evidence; repeating installation is not a general recovery step.

CoreS3 0.21.6/0.21.7 remain compatible, UnitV2 service stays at 1.3.0 and SQLite
stays at schema 5. The speech, camera-language, reminder, tracking and presence
changes from 0.6.1 remain included. No claim of physical acceptance is made.
