# Kadence daily use

Use `C:\KadenceX\source` on `kadence/rebuild-kade` with the matching RC1 firmware.
Stop an existing `kadence` process with Ctrl+C before updating or flashing.
Download mode is appropriate while flashing; the host verification before it
does not contact the device. After a successful flash, reset into normal boot
if the device remains in download mode, then start `kadence`.

## Candidate update

From the repository root after pulling the current branch:

```powershell
.\rebuild\tools\deploy.ps1 -Port COM4
```

This fetches the current remote, checks the host, builds once and flashes once.
It stops at the first failed gate. It does not delete generated files or reset
your checkout. A prebuilt bundle avoids the local build:

```powershell
.\rebuild\tools\deploy.ps1 -Port COM4 -Bundle "$env:USERPROFILE\Downloads\Kadence-RC1.zip"
```

The prebuilt bundle and source commit must match exactly. Do not flash images
from older branch layouts or substitute a historical combined binary.

Host-only maintenance, when the installed firmware is already compatible:

```powershell
.\rebuild\tools\deploy.ps1 -HostOnly
```

This repairs the host dependencies and runs the startup and candidate checks
without building or flashing. The startup fix after `ff7a422` is host-only and
uses the firmware already flashed from that commit.

## Ordinary startup

```powershell
kadence
```

For visible credential entry in the owner's private lab:

```powershell
python -m kcore.appliance --visible-input
```

The module command starts the same runtime using this terminal's Python. Use it
after `deploy.ps1` to avoid a stale `kadence.exe` from a different environment.
SDK build/flash setup now runs in a child process and leaves the host environment
intact. `python -m kcore.appliance --check` verifies dependencies and timezone
before asking for credentials or touching the device.

Provider credentials are read from `OPENAI_API_KEY` and `GEMINI_API_KEY` (or
`GOOGLE_API_KEY`). If absent in an interactive terminal, Kadence asks locally
with hidden input by default; `--visible-input` shows all three credential entries
locally as requested by the owner. They are used only in this process. Wi-Fi credentials also
remain local inputs; firmware holds them in RAM only. Never paste secrets into chat.

Wait for `KADENCE_RUNTIME DEVICE ready`. Touch once and speak when the device
indicates listening. Touch during an active turn to cancel. Let a response finish
before the next touch. The current capture window remains 4.8 seconds. If asked
to confirm a change, use a new turn to say yes or no.

Ctrl+C stops the host. A CoreS3 reset should reconnect automatically while the
host stays running. Do not open another serial monitor alongside `kadence`.

## Local configuration

`--port` overrides COM4. `KADENCE_LAN_HOST` selects the PC's reachable LAN IPv4
address if a VPN or multiple adapters cause incorrect automatic selection.
`KADENCE_TIMEZONE` defaults to `Europe/London`.

Explicit local records reside in `%LOCALAPPDATA%\Kadence\context.sqlite3` on
Windows. `KADENCE_DATA_DIR` overrides that directory. To back up the database,
stop Kadence and copy the whole directory. Conversation history is process-only;
audio and automatic transcripts are not persisted.

Optional integration configuration is defined in `backend/kcore/integrations.py`.
Only configure services you own and intend Kadence to access. No optional account
is required to start the normal runtime.

For diagnostics, retain the first error and the subsequent recovery lines.
Do not share credentials, complete voice payloads or private database contents.
