# RC1 engineering record — no feature reveal

RC1 is a candidate for physical acceptance, not a claim of new hardware sign-off.
Phase A's historical acceptance remains valid at its recorded source anchors.

## Boundaries

- `tool_bridge.py` implements `ToolBridge.invoke` with a closed registry, strict
  schemas, bounded JSON results, per-handler deadlines and cancellation propagation.
  Synchronous handlers are rejected. Registered handlers are trusted project code;
  arbitrary Python, shell, file paths, URLs and device objects are not tools.
- A timed-out coroutine is cancelled and quarantined without holding serial,
  voice or body ownership. There are at most four outstanding handler tasks.
- `companion.py` accepts one bounded JSON proposal per turn. It does not use
  provider-native recursive function calls or parse natural-language claims as
  execution proof. A model-proposed mutation needs a locally generated spoken confirmation and a
  subsequent explicit affirmative response within 60 seconds. Narrow, explicit
  local save/add commands already authorize their reversible operation, without
  a redundant confirmation. A model cannot set
  the authorization flag. A new topic, cancellation, disconnect or failed playback
  discards pending authorization.
- Volatile history is limited to eight completed exchanges and 12,000 characters.
  Only the device's successful voice ACK commits history. Reconnect preserves
  completed history; restarting the process clears it.
- Explicitly authorized local records use SQLite transactions and parameterized
  queries, with bounded records/results and a 250 ms database busy timeout.
  The database stores no audio or automatic transcript history. Blocking SQLite
  work runs outside the asyncio event loop. A cancelled or timed-out write can
  already have committed; it is never automatically retried or claimed rolled back.
- Integration destinations are owned by code or explicit local configuration.
  HTTP reads have deadlines, 64 KiB response limits and redirects disabled.
  Missing optional integration configuration does not stop the appliance.

## Wire and device

The normal host generates a fresh 128-bit token for each physically initiated
turn and sends it over the existing serial control command. The device sends
`KDV2`, 16-bit network-order 16000 and 60, then 32 ASCII hex token bytes, followed
by the existing length-prefixed Opus packets and zero terminator. `KDR1` PCM and
`KDE1` error framing are unchanged. Tokens are single-turn, never logged, and
invalidated on cancel, completion or reconnect. Idle LAN clients and repeat
connections are rejected before providers run.

Legacy `KDV1` remains available only to explicitly invoked diagnostic listeners.
The normal tool-capable appliance requires KDV2. Old normal firmware therefore
needs the matching RC1 flash. This is bearer authentication on the existing local
TCP transport, not TLS; it does not promise protection against traffic interception.

The avatar renderer is a hardware-free C++ scene with the existing eleven-state
contract. A fixed 150 KiB PSRAM canvas drains through an internal 5 KiB scratch
buffer and the existing synchronous LCD boundary. DMA never receives the canvas
pointer. RGB565 words are explicitly serialized high-byte first for the existing
ILI9341 SPI driver, with native primary-colour and buffer-canary checks.
A transfer timeout prevents buffer reuse until reset. A failed canvas
allocation falls back to the previous local renderer. Touch and attention are
published atomically without a second I2C or touch reader.

Speaking is entered only when staged PCM is ready for actual playback. The audio
meter reads samples on the existing capture/playback owners. No second I2S task,
codec, serial reader or motor execution path was added. RAM-only Wi-Fi credentials,
calibration, motion completion/release ACK ordering and PSRAM/DMA audio staging
remain intact.

## Reproduction and delivery

- Python 3.12; host package `0.2.0`; firmware `0.20.0`; ESP-IDF 5.5.4.
- This hosted Linux build uses IDF Component Manager 2.2.2, within the SDK's
  `~=2.2` requirement. Newer versions assume process information unavailable in
  this workspace. No SDK hardware or access-control code was modified.
- Native renderer QA uses AddressSanitizer and UndefinedBehaviorSanitizer.
  LeakSanitizer is disabled only in the hosted local check because process
  enumeration is unavailable. CI runs the normal sanitizer executable.
- `python -m pytest rebuild/tests -q` covers existing and new behavioral tests.
  `phase_b_gate.py` is the compact candidate test entry.
- Current foundation, cancellation, self-init, audio staging and ordinary-runtime
  architecture gates remain in CI. Obsolete historic entry/version selectors are
  not applicable to the current firmware entry.
- `package_firmware.py` copies the real IDF manifest paths, checks chip, flash
  geometry, expected offsets and partition capacities, and creates SHA-256 hashes.
  Only bootloader, partition table, initial OTA data and factory application are
  writable. NVS calibration and product storage regions are excluded.
  CI passes its checkout SHA explicitly: Docker checkout ownership can prevent
  a separate Git process reading HEAD. Local packaging still uses local HEAD.
  A CLI regression test verifies packaging without Git access; no global Git
  ownership exception is required.
- `deploy.ps1` fetches the actual branch, refuses tracked local edits/divergence,
  checks a prebuilt bundle's exact source commit, installs the host and runs its
  candidate gate before flashing. Without a bundle, it builds once locally.

## Remaining acceptance

Local verification after the Windows handle fix: **56 tests passed, 18 subtests passed**;
the focused Phase B suite contains **35 tests**. CP23, A4, A3 cancellation,
self-init and voice-wire gates passed. The native renderer passed all eleven
state/bounds checks with AddressSanitizer/UndefinedBehaviorSanitizer enabled.
ESP-IDF 5.5.4 completed the full build; application size was approximately 1 MiB,
leaving 76% of its 4 MiB partition free. Flash offsets and SHA-256 manifests are
validated by the package step.

The first operator deployment stopped before flashing: Python 3.14 on Windows
reported fourteen temporary-database cleanup errors (`WinError 32`). SQLite's
transaction context had been used without explicitly closing its connection.
Both initialisation and operation workers now close their own connection after
commit/rollback, including exception paths. Three tests retain real connections
to prevent garbage collection hiding leaks; all three fail on the old code.
CI now runs the host suite and deployment gates on Windows Python 3.12 and 3.14,
and parses both operator scripts with Windows PowerShell. Download mode was
unrelated to this failure; the guard stopped before the serial flashing step.

The new combined candidate needs physical cold start, rendering/touch responsiveness
under audio load, normal/repeated conversation, one safe tool round-trip, explicit
confirmation, cancellation during work/playback, forced external failure, device
reset/reconnect, and clean restart. Public-service adapters are tested with bounded
HTTP fixtures; the user's live provider credentials and home environment were not
available in this workspace. Do not label B4 or the complete product signed off
until those physical observations are recorded.

API references: [Open-Meteo](https://open-meteo.com/en/docs),
[Home Assistant REST](https://developers.home-assistant.io/docs/api/rest/).
