# Kadence RC1 — owner acceptance

**Status: APPROVED by Boss on 7 September 2026.**

| Item | Accepted baseline |
|---|---|
| Repository / branch | `neoncrucible/StackChanSource` / `kadence/rebuild-kade` |
| Source commit | `997654857c3dd6aa2f78c92501c2eda2bf6744fe` |
| Host / firmware | `0.2.0` / `0.20.1` |
| Hardware | StackChan K151 / CoreS3, ESP32-S3, USB COM4 |
| Host environment | Owner's Windows PowerShell installation |
| Operator guide | [Kadence operator manual](USER_MANUAL.md) |

The owner reported a successful flash, started the normal appliance with local
visible credential entry, completed a touch-initiated spoken interaction and
explicitly requested approval/sign-off of this build.

The following credential-free excerpt records the observed lifecycle:

```text
KADENCE_FLASH PASS. Start the matching host with kadence.
KADENCE_RUNTIME DEVICE ready presence=local
KADENCE_RUNTIME TURN start trigger=touch
KADENCE_RUNTIME PROVIDERS complete transcript_chars=32 reply_chars=163 pcm_bytes=314880
KADENCE_RUNTIME TURN complete seq=1 voice=1 body_reaction=1 idle_return=1
KADENCE_RUNTIME STOPPED clean=1
```

This establishes flash completion, ordinary host/device startup, a completed
voice-provider round trip, completed device voice playback, the body reaction,
return to idle and clean host shutdown in the approved run. The avatar had also
been positively observed by the owner.

The build's existing verification includes 65 host tests and 18 subtests, a
44-test focused Phase B gate, native renderer and Wi-Fi state checks, Windows
Python 3.12/3.14 verification and the ESP-IDF firmware build. The matching
[CI run](https://github.com/neoncrucible/StackChanSource/actions/runs/34143759796)
completed successfully. Those checks are automated evidence, distinct from
the physical run above. Earlier Phase A acceptance remains recorded in
[the handover](KADENCE_HANDOVER.md).

Owner acceptance of RC1 is complete. This record does not claim that the latest
single-turn log separately exercised every optional integration, stored-data
operation, cancellation case or extended endurance condition. Those remain
regression scenarios for subsequent development, rather than a reason to reopen
the owner's approval.

## Next work and authority

The owner requested a proposal for a themed Windows server UI, useful and fun
utilities, top LED animations, top-touch volume, and camera capabilities including
object recognition, face tracking and recognition of enrolled people.

**Research and proposals are authorised; implementation of these changes requires
the owner's next explicit sign-off.** The owner also authorised this manual to
describe all current features. Preserve unrelated unrevealed surprises. Approval
of RC1 does not approve any future feature proposal.

Documentation changes after the accepted source do not change the installed
firmware or require another flash. Preserve the original release's source identity
and hashes. A later build from a documentation commit is a separately identified
artifact; do not relabel the physically accepted ZIP.
