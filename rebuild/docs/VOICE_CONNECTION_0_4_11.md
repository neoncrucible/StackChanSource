# Host 0.4.11 — robot audio connection

The 26 September 20:55 UTC export reports a robot `tcp-connect` failure (116)
before recording, then a USB reconnect without a completed voice turn. It does
not establish a provider, microphone or speech-synthesis fault. The export does
not contain network addresses or Windows firewall rules, so the exact network
cause remains unconfirmed.

The installer uses a different executable path for each release. Windows
application firewall rules use executable paths; an allowance for an older
Kadence installation may therefore not cover an update. A stale explicitly
selected PC address, a VPN route or network isolation can also prevent this
robot-to-PC connection. The new checks distinguish local configuration evidence
from an actual confirmed audio exchange.

## Restore and check audio

1. Quit the old tray instance, extract the complete download, run
   `Install-Kadence.cmd` and launch the existing desktop shortcut. Verify 0.4.11.
2. Start the server. Overview now contains **Test Audio Link**, **Check Network**
   and **Allow Robot Audio**. The network check also runs in the background.
3. Follow the network result. **Allow Robot Audio** asks Windows for administrator
   permission and creates/updates Kadence's own inbound TCP allowance for this
   executable, restricted to Private networks and the local subnet. It never
   turns off Windows Firewall, changes a network to Private, opens Public
   networks, or removes another application's rules. If an explicit block rule
   applies, review it in Windows Firewall; block rules take precedence.
4. Use **Test Audio Link**. This sends two short tones through the existing
   authenticated robot audio path and requires both the media exchange and the
   robot's playback acknowledgement. It uses the selected output, no microphone,
   no AI service, no conversation history and no camera. Cancellation remains
   available. A passed link test does not test microphone input or AI credentials.
5. Tap the robot once, wait for the recording cue/countdown, then speak. A second
   tap cancels the attempt. Check an ordinary question, then “what can you see?”.

If Windows calls a trusted home connection Public, change that connection's
profile in Windows Settings yourself before using the Private-network allowance.
If an allowance is present but the link still fails, check the selected PC LAN
address and whether the router isolates guest/Wi-Fi clients. The local network
check cannot prove that traffic passes a router, a third-party firewall or policy.

## Behavior changes

- Auto selection can prefer the configured Wi-Fi's physical adapter over a VPN
  or the UnitV2 USB network. Explicit PC addresses and the environment override
  remain authoritative. Windows discovery runs outside the voice turn; per-turn
  address checks are local socket operations.
- Voice, alerts, greetings and robot snapshots refresh/check their endpoint.
  An address no longer assigned to the PC is reported before sending a voice
  command or credentials to the robot.
- A TCP failure with confirmed release leaves the USB control session available.
  Resetting that session cannot install a firewall rule. Wi-Fi/device stalls and
  unconfirmed cancellation retain the bounded supervisor recovery path.
- Alert playback has connection/playback deadlines as normal voice already did.
  A lost ACK cannot keep a greeting or audio check busy for 190 seconds.
- USB reconnection says audio is unverified. Only the audio test's authenticated
  exchange and device ACK produce a passed result. Touch cancellation is visible.
- Exports add only enumerated network outcomes and booleans/counts. They exclude
  addresses, SSIDs, executable paths, credentials and arbitrary exception text.

No firmware flash, UnitV2 reinstall, schema change or speech-provider change.
The owner's accepted scene descriptions remain under regression coverage.

## Evidence and limitations

Local suite: 330 passed, 119 subtests, four Windows-only skips. The ownership and
alignment gate passes. New real-socket checks cover failure then successful audio,
missing/fabricated playback proof, touch cancellation and stale local addresses.
Windows CI must validate the actual COM rule in memory without registering it,
execute the read-only inventory helper and verify both in the packaged program.
Hardware microphone, speaker and home-network acceptance cannot be performed here.

The same export exposes a separate training problem: the longer attempt reached
9/20 accepted samples and no saved-profile event; all matching records had zero
compatible enabled samples. This release prioritizes the immediate voice outage.
It does not claim to fix or accept live enrollment/greetings. The all-or-nothing
training workflow still needs a usable save/refinement path and better rejection
evidence; do not describe this as a similarity-threshold failure.

Microsoft references:
- https://learn.microsoft.com/en-us/windows/win32/api/netfw/nn-netfw-inetfwrule
- https://learn.microsoft.com/en-us/windows/win32/api/netfw/nn-netfw-inetfwpolicy2
- https://learn.microsoft.com/en-us/powershell/module/netconnection/get-netconnectionprofile
