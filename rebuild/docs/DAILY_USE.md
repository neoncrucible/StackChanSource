# Kadence daily use

RC1 is owner-approved: host 0.2.0 / firmware 0.20.1 at source `9976548`.
The complete [operator manual](USER_MANUAL.md) covers all current features,
configuration, saved records and software maintenance.

## Start

Keep the robot in normal boot mode, connected by USB and on a Wi-Fi network
reachable from the PC. Open PowerShell and run:

```powershell
cd C:\KadenceX\source
python -m kcore.appliance --visible-input
```

Enter credentials locally. Omit `--visible-input` for hidden entry. Wait for
`KADENCE_RUNTIME DEVICE ready presence=local`.

## Use

- Tap the front touchscreen once, wait for listening and speak a short request.
  The default capture lasts 4.8 seconds.
- Let Kadence finish speaking and return to idle before starting another turn.
- Tap during an active turn to cancel.
- When asked to confirm a stored change, start a new turn within 60 seconds and
  say yes or no.
- A device reset reconnects automatically while the host remains running.

## Stop

Press Ctrl+C and wait for `KADENCE_RUNTIME STOPPED clean=1`. Stop before flashing
or opening another serial monitor. Keep credential-entry lines out of shared logs.

## Maintenance

This manual/sign-off update needs no reflash. Keep using the approved installation.
Future releases need a matching source and bundle; the deploy script checks the
full commit, including documentation commits. Follow the new release's supplied
filename and commands. See [software maintenance](USER_MANUAL.md#9-software-maintenance)
for the supported deployment options.

For a dependency/timezone check without credentials or device access:

```powershell
python -m kcore.appliance --check
```
