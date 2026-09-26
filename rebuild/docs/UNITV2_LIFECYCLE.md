# UnitV2 start / stop — hosts 0.4.4 through 0.4.6

This release controls the actual `camera_stream` process on UnitV2. It keeps
the accepted 0.4.3 voice path and firmware 0.21.6. No robot firmware flash.
Automatic perception remains paused in 0.4.4. In 0.4.5 it is a separate opt-in;
leave it unchecked until this lifecycle acceptance pass succeeds. No second
camera-service installation is needed when updating from 0.4.4 to 0.4.5.

## One-time setup

1. Install the complete desktop package with `Install-Kadence.cmd`.
2. Open Vision. Check the UnitV2 address (currently `192.168.40.175`, assigned
   by DHCP), then click **SET UP UNITV2**. Kadence stops its host server first.
3. In the setup window press Enter to install. Enter the camera's existing
   SSH password when OpenSSH or sudo asks. Host fingerprint checking stays
   enabled; Kadence never stores that password.
   Host 0.4.6 first verifies the Linux null character device and restores its
   standard 0666 permissions if necessary. The factory image can recreate it
   as root:root 0660 after reboot, preventing SCP even with a correct password.
   This check runs before each setup/restore; no startup scripts are changed.
4. When setup says complete, unplug and reconnect **UnitV2 power**. Wait for
   its normal boot. Start the Kadence server.

Setup verifies the installed factory Python service and camera executable
against the exact M5Stack 7 September 2021 recovery image before replacing
any camera-service files. Unknown builds are refused. The original entry is backed up at
`/home/m5stack/payload/server_core.kadence-original.py`.

The new service replaces the factory recognition web application while
installed. Its original supervisor, camera executable, Wi-Fi settings, Linux
image and SD card contents are retained. The old browser preview is not used.
The original web application can be restored through **SET UP UNITV2**, option
**R**, followed by another UnitV2 power cycle. Restore does not undo Wi-Fi.

If 0.4.4/0.4.5 setup fails with `Couldn't open /dev/null: Permission denied`,
the file copy failed before the service installer ran. Either use 0.4.6 or run
this once in Windows PowerShell and then retry SET UP UNITV2:

```powershell
ssh -t m5stack@192.168.40.175 'test -c /dev/null && sudo chmod 666 /dev/null && ls -l /dev/null'
```

Use the camera's actual address if DHCP changed it. Password prompts are for
SSH and sudo; the factory `m5stack` password is `12345678` unless changed. Expect
`crw-rw-rw-` for `/dev/null`. This repair alone does not install the service.

The generated pairing key stays in Windows Credential Manager and a protected
camera file. Requests use a signed, single-use challenge; no password/key is
sent over HTTP or included in diagnostics. Image transport is ordinary LAN
HTTP; use your trusted local network.

## Normal controls

| Control | Behaviour |
| --- | --- |
| ON DEMAND | Starts the producer for a requested frame/burst, then confirms its exit. Default after host restart. |
| KEEP READY | Keeps the producer running while Kadence renews its lease. Explicit, session-only choice. |
| STOP NOW / STOPPED | Cancels capture, requests producer exit and pauses automatic visual work. An explicit manual Capture can still take one frame and stop again. |
| Privacy | Immediately revokes host access and clears preview, then requests producer stop. Keep-ready start is blocked. |
| REFRESH STATUS | Reads actual service/process status; does not start capture. |
| TEST START / STOP | Runs two fresh-frame / confirmed-stop cycles, showing the last image. |

The successful test saves a small local verification record tied to the pairing
key and service version. A changed pairing requires another test before enabling
automatic UnitV2 perception. This proves the API/process cycle, not electrical
power-off or recognition accuracy.

Capture state (IDLE/CAPTURING), automatic policy (OFF/EVENT_ONLY/AWARE), and
UnitV2 producer status are separate. Closing a preview is not a producer stop.
`STOPPED · stop confirmed` means the managed camera process has exited and its
reader is settled. It does not mean the UnitV2 board, sensor or ISP is powered
off. Power, cooling and electrical standby have not been measured.

If the laptop exits or loses Wi-Fi, a running lease expires **on UnitV2** after
30 seconds without renewal. No browser visit is needed after reboot. A normal
host shutdown requests immediate stop. If a request fails, the console says
STOP_UNCONFIRMED rather than claiming success. Refresh once connectivity
returns. A camera-service crash or factory button restart can leave an
unowned producer; the new service reports a conflict and requires a power
cycle instead of killing an unknown process.

## One acceptance run

1. Keep policy OFF and privacy off. Select UnitV2. **TEST START / STOP** must
   report PASS after two images, leaving `STOPPED · stop confirmed`.
2. Select KEEP READY / APPLY MODE, then CAPTURE. Move an object and capture
   again; confirm a fresh image. STOP NOW must confirm stopped.
3. Enable Privacy. Capture and KEEP READY must be blocked; producer remains
   stopped. Disable Privacy and repeat one capture.
4. Quit and reopen Kadence, then repeat TEST START / STOP without opening the
   factory camera page. Check an ordinary voice answer and head alignment.
5. Optional lease check: KEEP READY, disconnect laptop Wi-Fi for 35 seconds,
   reconnect and REFRESH STATUS. Expect stopped and an increased expiration
   count. Select ON DEMAND to resume normal use.

The original CoreS3 two-click capture quirk remains accepted. If setup is not
installed/paired, explicit legacy UnitV2 capture is retained but lifecycle is
shown as SETUP_REQUIRED. Automatic perception must never use that legacy path.

## Provenance and validation

Factory source: M5Stack's official
[recovery package](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/firmware/UnitV2/M5UnitV2RootfsRecoveryPackage-09072021.zip),
linked from its [update documentation](https://docs.m5stack.com/en/compute/unitv2/update).
The archive was extracted read-only to inspect the actual service, supervisor
and executable. No factory code or binary is redistributed in this package.

- Recovery ZIP SHA256: `c36022a56f101608625571115a9c0165f9a203151b58f69e1379ee53483f88da`
- Factory `server_core.py`: `4cbdcc26903effc52638e0a85e7c463991087235e8b4e70d64b35e150ba05d74`
- Factory `bin/camera_stream`: `a2203a4700445ee62feec8e5c645cf6ae05211e01ba2153ce555519f62f20b92`

The vendor [framework](https://github.com/m5stack/UnitV2Framework) reads a
`_{"stream":1}` system command and writes JSON lines containing base64 JPEGs.
Its stream-disable flag only suppresses transmission; the capture loop
continues. The Kadence service instead owns and waits for the process itself.

Automated tests exercise real child processes and real loopback HTTP, fresh
frame sequencing, authenticated operations, expiry, cancellation, concurrent
ownership, error reporting and reversible install guards. Physical UnitV2
acceptance is still required; desktop CI cannot prove the camera's sensor or
electrical behaviour.
