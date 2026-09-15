# ToF4M measurement bring-up

Candidate: host **0.3.5**, firmware **0.21.6**, branch `kadence/sensor-clean-base`.
Physical acceptance is pending. Keep the camera-tested 0.21.5 bundle
`Kadence-RC2-Firmware-038f203eb094` for comparison if needed.

The owner requested this order: confirm ToF4M measurements, integrate UnitV2-M12,
confirm coexistence, then add functionality using the sensors. This candidate
adds distance diagnostics only. No movement, automatic capture, LLM input,
gesture action mapping or recognition behavior is attached to these readings.
UnitV2 is not changed in this candidate.

## Wiring and implementation

| Component | Connection | Evidence |
| --- | --- | --- |
| PaHub at 0x70 | CoreS3 red Port A | Existing verified hub |
| Gesture PAJ7620U2 | Hub channel 0, 0x73 | Existing directional measurements |
| ToF4M VL53L1X | Hub channel 1, 0x29 | Previously address discovery only; new measurement driver |
| UnitV2-M12 | Separate later integration | Do not attach it to the I2C hub |

One existing worker owns discovery, Gesture and ToF traffic on external I2C0
(SDA2/SCL1). Internal I2C1 and camera DMA configuration remain unchanged. ToF
adds a 16-bit register interface; Gesture retains its 8-bit interface. Every
measurement turn selects and verifies one channel, performs one register
transaction, and deselects/verifies isolation. Each I2C operation has a 10 ms
timeout; no measurement turn makes more than five calls. Discovery and register
turns alternate; Gesture and ToF alternate register turns. No new task is added.

Initialization checks model/module ID **0xEACC**, then boot status, stops ranging,
loads the ST default configuration in at most 16-byte chunks, and performs the
ULD initial VHV sequence with bounded polling. It uses AVDD I/O mode as M5's
reference Pololu driver does. Long mode uses a 200 ms budget and a calibrated
250 ms intermeasurement period. Host-visible sample rate is lower and has gaps
during discovery sweeps; this is a diagnostic integration, not a 50 Hz stream.

Result status and millimetres come from one 17-byte read. The result is published
only after interrupt clear succeeds. Only raw status 9 (ULD valid) and 40–4000 mm
produce a valid distance; other results return `distance_mm: null`. This range
check does not guarantee four-metre performance for every target or lighting.
A sensor that ACKs but never boots or becomes data-ready has a five-second
wait deadline, allowing for normal discovery pauses. Transport/identity/timeout
faults invalidate the distance and use existing 60-second channel quarantine;
failed deselection faults the hub. An absent sensor is unavailable, not zero mm.

`sensors.tof` is an empty-payload, read-only cached query on the existing serial
owner. Schema 1 carries state, channel/address, sequence, sample age, errors,
raw status, validity and nullable distance. `fresh` requires ready, sequence >0
and age <=3000 ms. Freshness and measurement validity are separate. Invalid or
stale data is never displayed as a current distance by `tof_status.py`.

Primary implementation references:

- [M5 ToF4M reference includes Pololu VL53L1X](https://github.com/m5stack/M5Unit-ToF4M/blob/main/src/M5_ToF4M.h).
- [Pololu initialization: model ID and I/O mode](https://github.com/pololu/vl53l1x-arduino/blob/master/VL53L1X.cpp).
- [ST ULD register table, timing and result decoding](https://github.com/stm32duino/VL53L1X/blob/5aa46e743913186c448aaf86dd0f12071fddc0a2/src/vl53l1x_class.cpp).

The adapted ST table/sequence retains the BSD notice in
`firmware/main/third_party/VL53L1X-LICENSE`; firmware bundles include third-party
notices and their hashes. No Arduino runtime dependency is introduced.

## Windows build and flash, including a fresh PowerShell session

Quit Kadence fully, including any tray instance. Keep COM4 free of serial
monitors. With the robot off, keep the existing Gesture/ToF wiring above and
then power it on. Pull and build:

```powershell
Set-Location 'C:\KadenceX\source'
git pull --ff-only origin kadence/sensor-clean-base
Set-Location 'C:\KadenceX\source\rebuild\firmware'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'C:\KadenceX\source\rebuild\tools\build_firmware.ps1'
```

The build helper loads ESP-IDF 5.5.4 itself. Expect `KADENCE_PACKAGE PASS`.
Derive the matching bundle from the checkout SHA (do not pick a ZIP by date):

```powershell
Set-Location 'C:\KadenceX\source\rebuild\firmware'
$kadenceCommit = (git -C 'C:\KadenceX\source' rev-parse HEAD).Trim()
$kadenceBundle = Join-Path 'C:\KadenceX\source\rebuild\dist' ('Kadence-RC2-Firmware-' + $kadenceCommit.Substring(0,12))
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kadenceBundle 'flash.ps1') -Port COM4
```

Expect all hashes verified and `KADENCE_FLASH PASS`. The package retains the
existing flash geometry and calibration preservation. Do not erase all flash.

## Physical acceptance, one stage at a time

1. With the desktop still closed, run the combined observation tool:

```powershell
Set-Location 'C:\KadenceX\source\rebuild'
uv run --no-project --python 3.12 --with 'pyserial>=3.5,<4' '.\tools\tof_status.py' --port COM4 --seconds 90 --gesture
```

Opening serial can restart the robot; initial starting/unavailable output is
not a measurement failure. Allow initialization to finish, including Gesture's
longer register sequence. Aim ToF at a flat matte target roughly 10 cm, 30 cm,
then 1 m from the sensor face, holding each for several seconds. Expect changing
distances near 100/300/1000 mm, increasing sequence, `fresh=True`, `valid=True`,
and no growing errors. Record actual values; this is a functional check, not
precision calibration. Wave separately in front of Gesture and verify its event
sequence still advances while ToF continues measuring. Aiming into empty space
or at unsuitable surfaces may give a fresh but invalid result; no false zero.

2. Let the tool exit, then launch the same checkout's desktop:

```powershell
Set-Location 'C:\KadenceX\source\rebuild'
uv run --project . --python 3.12 --extra voice --extra desktop kadence-desktop
```

Allow the sensor initialization to settle. Check a complete voice reply,
cancellation followed by a new reply, a one-shot reminder, and the built-in
camera after voice. The owner accepts Capture sometimes needing a second click;
do not reopen that UI issue. If there is a failure, export Diagnostics and
identify which check failed rather than accepting address discovery as ranging.

3. Once ToF and coexistence are physically confirmed, record the results in the
handover before integrating UnitV2-M12. Start UnitV2 work by confirming its
current USB/network connection and working camera endpoint on this Windows PC.
Retain the built-in camera as the tested path while adding the separate camera.
No recognition or autonomous sensor behaviors until all integration checks pass.
