# Kadence sensor Phase 1 — Windows startup and test commands

Recorded from the owner's successful setup and hardware session on 2026-09-13.
Run PowerShell commands one at a time. Use normal Windows PowerShell; SDK build
and flash helpers run in child processes.

## Tested installation

| Item | Value |
| --- | --- |
| Source checkout | `C:\KadenceX\source` |
| Source branch | `kadence/sensor-clean-base` |
| Tested firmware source | `a73c936da3e9305c06987c2e56bfe0fe61351161` |
| Firmware | `0.21.3` |
| Console | `0.3.2`, sidebar build `1d4db2820820` |
| Installed console folder | `C:\KadenceX\apps\Kadence-RC2-1d4db2820820` |
| Robot USB port | `COM4` |
| ESP-IDF | `C:\Espressif\frameworks\esp-idf-v5.5.4` |
| Hub input | Red Grove Port A on the CoreS3: SDA GPIO2, SCL GPIO1 |
| Tested hub configuration | Factory address `0x70`, all six outputs empty |

The CI console was built from merge commit
`1d4db2820820a3f3e062d47b460fe9c2d2c4db85`. Its tree matches firmware source
`a73c936`; different package suffixes do not indicate different source content
for this specific verified pair. [Successful CI run](https://github.com/neoncrucible/StackChanSource/actions/runs/34758311792).

An older RC2 console in Downloads still has Play Games. Use the installed path
below. Pulling source and flashing the robot do not replace that older executable.

## Start after a cold Windows boot

1. Connect Kadence by USB and boot normally. Leave all new modules disconnected
   unless deliberately repeating the empty-hub test. Download mode is for flashing.
2. Launch the known console:

   ```powershell
   Start-Process -FilePath 'C:\KadenceX\apps\Kadence-RC2-1d4db2820820\Kadence.exe' -WorkingDirectory 'C:\KadenceX\apps\Kadence-RC2-1d4db2820820'
   ```

3. Check the sidebar says `1d4db2820820` and Play Games is absent. Click
   **Start server** and wait for **Robot connected**. Keep USB connected and
   Windows awake. Connection settings and credentials are entered in the app.
4. Tap the front screen, wait for the listening cue / REC indication, then
   speak. Tap during a longer reply to cancel; wait for idle before a new turn.

Use **Stop** to release the robot connection. Use **Quit**, including the tray
icon, before flashing or running the standalone serial diagnostic. Merely closing
the window can leave the server running in the tray.

## Read sensor health

Close Signal Console completely, keep Kadence normally booted, and run:

```powershell
uv run --no-project --python 3.12 --with 'pyserial>=3.5,<4' 'C:\KadenceX\source\rebuild\tools\sensor_status.py' --port COM4 --watch 3
```

The diagnostic exits after three samples and releases COM4. Reopen the console
to resume voice service. Do not run both serial owners at once.

This PC has Python 3.14 and uv-managed CPython 3.12.13. Its launcher tag for 3.12
is `Astral/CPython3.12.13`; `py -3.12` failed, and directly selecting that bare
runtime failed because `pyserial` was missing. The tested uv command supplies
the dependency in its run environment.

| Physical setup | Expected completed snapshots |
| --- | --- |
| No hub | `hub=absent`, `fresh=True`, increasing sequence, six unavailable channels, no responses, zero errors. |
| Empty hub on red Port A | `hub=ready`, `fresh=True`, increasing sequence, six ready channels, no responses, zero errors. |

A first `starting`, sequence 0, `fresh=False` snapshot means the first sweep has
not completed. The owner observed a restart on opening the diagnostic; the
following two snapshots were fresh and stable. Do not count an incomplete
snapshot as a failed hub detection. The printed ENV III address warning is a
fixed reminder and does not mean an ENV sensor was detected.

For hardware changes, stop the server, disconnect USB and power Kadence fully
off before connecting/removing the hub. Use the red socket on the CoreS3, leaving
the blue/black body sockets unused for this test. Keep all hub outputs empty.

## Install the tested Windows ZIP again

The verified release file is `Kadence-RC2-1d4db2820820.zip`. GitHub's
`kadence-rc2-windows-complete` artifact is an outer ZIP containing that release
ZIP; extract the inner release in full. A verified copy of the inner ZIP was
provided directly in the conversation after the browser download returned 404.

With that release ZIP in Downloads and the old console fully quit:

```powershell
Expand-Archive -LiteralPath 'C:\Users\denma\Downloads\Kadence-RC2-1d4db2820820.zip' -DestinationPath 'C:\KadenceX\apps\Kadence-RC2-1d4db2820820'
```

The destination was new in this session. If it already contains the working
application, launch that installation; do not overwrite a running copy. Keep
`Kadence.exe`, `_internal` and the other extracted files together. Replacing the
desktop application alone does not require reflashing the already-tested 0.21.3
firmware.

## Build and flash when a firmware change requires it

Daily startup does not require these steps. Keep the last tested package before
building another candidate. Check the branch and local edits first:

```powershell
git -C 'C:\KadenceX\source' status --short --branch
```

With a clean `kadence/sensor-clean-base` checkout:

```powershell
git -C 'C:\KadenceX\source' pull --ff-only origin kadence/sensor-clean-base
```

Record the source ID for this build, then run the build in a child PowerShell:

```powershell
$kadenceBuildCommit = (git -C 'C:\KadenceX\source' rev-parse --short=12 HEAD).Trim()
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\KadenceX\source\rebuild\tools\build_firmware.ps1'
```

Wait for `KADENCE_PACKAGE PASS`. Do not change source revisions between these
steps. Package filenames use the current source ID; documentation commits also
change that suffix. The historical `a73c936da3e9` folder is not the output name
of every future build.

Quit the console and serial tools, disconnect new modules, connect USB and enter
download mode: hold RST for approximately three seconds until its green indicator
lights, then release. Flash the bundle created for the recorded source ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\KadenceX\source\rebuild\dist\Kadence-RC2-Firmware-$kadenceBuildCommit\flash.ps1" -Port COM4
```

Wait for `KADENCE_FLASH PASS`. Briefly press RST once if normal boot does not
resume. Do not hold it again for normal startup. The helper verifies hashes and
flash offsets and preserves calibration. Do not use the old `deploy.ps1` here;
it targets `kadence/rebuild-kade`.

Packages already built on the owner's PC:

- Tested Phase 1: `C:\KadenceX\source\rebuild\dist\Kadence-RC2-Firmware-a73c936da3e9`.
- Earlier clean-base fallback: `C:\KadenceX\source\rebuild\dist\Kadence-RC2-Firmware-9091e7e2112b`.

## Current test status and next hardware

See [the owner test record](ASTRA_SENSOR_INTEGRATION_HANDOVER.md#12-owner-hardware-tests--2026-09-13)
for individual results. Bus discovery, voice/cancel, camera, reminders and
boot/voice after hub removal passed. **App volume failed**, reported pre-existing;
top-swipe volume is an older unresolved issue. Neither is a current PASS.

No ENV, ToF, gesture or external vision module was qualified in this test.
Keep them disconnected until the model and hub revision are verified. ENV III's
QMP6988 uses `0x70`, conflicting with the factory hub address. Physical hub
address selection and `CONFIG_KADENCE_SENSOR_HUB_ADDRESS` must match before
attaching ENV III. Do not guess a DIP-switch pattern for an unidentified hub.
