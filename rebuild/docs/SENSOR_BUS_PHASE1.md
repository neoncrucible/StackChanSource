# Sensor bus Phase 1 — firmware 0.21.3

Base: `kadence/sensor-clean-base` at `5771a006300a2f3c616be449b983e890c2c77d47`.
Known physically tested fallback: `9091e7e2112bbdd9e08141196147ad9a8c2660d0`.
This candidate requires physical sign-off before Phase 2.

## Implemented boundary

| Owner | Responsibility |
| --- | --- |
| `sensor_runtime.cpp` | Own external I2C0 on Port A: SDA GPIO2, SCL GPIO1. Low-priority task, 4096-byte stack. |
| `sensor_bus.h` | PCA9548AP selection/isolation and incremental address discovery. Hardware-independent state machine. |
| `sensor_protocol.h` | Schema 1 bounded status and read-only command validation. |
| Existing Probe21 serial owner | Answer `sensors.status` from a cached snapshot. No I2C in this handler. |
| `kcore/sensors.py` | Validate and type discovery evidence for host callers. No automatic behaviour. |
| `tools/sensor_status.py` | Readable diagnostic using the existing serial transport. |

The internal I2C1 bus on GPIO12/11, voice/media ownership, avatar, Signal Console,
camera, front/top touch, reminders and device settings retain their current
implementation. The sensor service starts after normal body/presentation startup;
bus or task allocation failure is reported as `unavailable`, not a boot failure.
No sensor task acquires a voice lock, writes settings, controls power rails,
changes motion, or sends unsolicited protocol events.

Each switch operation writes one control byte with a STOP, then checks the
read-back. Exactly one of the six exposed channels is selected. Each target
probe ends by writing and checking zero (all channels isolated), even after a
NACK or timeout. There is no cached selection to become stale after a hub reset.

Every I2C call has a 10 ms driver timeout. One worker step performs at most five
calls (select/read/probe/deselect/read), then yields for 20 ms. It probes one
target per step, never the entire bus in one blocking loop. New sweeps start
five seconds after completion/failure. No measurement commands are sent to
downstream devices: only address probes. Empty channels are healthy, with mask 0.

A downstream timeout quarantines that channel for 60 seconds if deselection
succeeds. Other channels continue. A failed selection/deselection invalidates all
downstream evidence and backs off at hub level. Missing hubs retry at the same
five-second interval without claiming a boot fault. Error counters saturate.

Electrical limitation: a device holding SDA/SCL low can prevent even the mux
deselect write. The Grove connection supplies no controllable RESET line. The
worker reports a hub fault; software cannot promise independent recovery of all
external channels from that condition. Power down and remove the offending
module/hub before restarting. The internal voice/touch bus is separate.

## Discovery and protocol contract

Command: normal v1 envelope, name `sensors.status`, empty payload `{}`, nonempty
correlation id below 48 bytes. It uses the existing single serial owner and ACK
registry. It does not wait for a scan or share the host media command lock.
Unsupported/malformed sensor requests are consumed without hardware writes.

Response payload:

| Field | Meaning |
| --- | --- |
| `ok`, `schema` | Query succeeded; schema 1. `ok` is independent of sensor health. |
| `seq` | Completed snapshot sequence. 0 means no scan has completed. |
| `age_ms` | Unsigned 32-bit elapsed milliseconds since publication; wraps after about 49.7 days. |
| `hub_address`, `hub`, `hub_errors` | Configured address; starting/ready/absent/fault/unavailable; cumulative bus errors. |
| `upstream_mask` | Address bits responding with every channel off, including the hub address if in the target list. These are excluded from downstream probes. |
| `channels` | Exactly six objects, indexed by physical port 0..5. Each has `state`, `mask`, `errors`. State is ready/quarantined/unavailable. |

Mask bit order is fixed for schema 1:

| Bit | Address | Possible device family; identification remains unproven |
| --- | --- | --- |
| 0 | `0x29` | ToF |
| 1 | `0x44` | SHT3x / environmental temperature-humidity |
| 2 | `0x45` | Alternate SHT3x address |
| 3 | `0x5C` | Earlier ENV DHT12 |
| 4 | `0x70` | ENV III QMP6988; also PaHub default |
| 5 | `0x73` | PAJ7620 gesture |
| 6 | `0x76` | BMP280 / pressure |
| 7 | `0x77` | Alternate pressure address |

These are a bounded target list, not a general-purpose I2C scanner. An ACK is
address evidence only. No temperature, distance, gestures, identity or sensor
validity is inferred from it. Upstream devices are excluded to avoid reporting
the same upstream address on all six channels. Duplicate downstream addresses
remain independently visible. If an upstream address collides with a downstream
one, this milestone deliberately cannot identify the hidden device.

A complete sweep is published atomically. The previous complete snapshot remains
readable during a scan; on hub failure all masks are cleared. Host readers mark
snapshots older than 15 seconds (or sequence 0) as not fresh. No LLM context or
action mapping is connected in this phase. The worst-width six-channel ACK,
including 47 control characters escaped in its id, is 843 bytes within the
unchanged 1024-byte frame allocation.

## ENV III address correction — resolve before Phase 2

The original handover mixed ENV generations. M5Stack specifies:

| Unit | Sensors | Default addresses |
| --- | --- | --- |
| ENV | DHT12 + BMP280 | `0x5C`, `0x76` |
| ENV II | SHT30 + BMP280 | `0x44`, `0x76` |
| ENV III | SHT30 + QMP6988 | `0x44`, `0x70` |

Check the delivered unit's model/SKU. If it is ENV III, the hub must not remain
at `0x70` when it is attached: the mux itself remains upstream when its channel
is selected. Use a non-conflicting hub address such as `0x71`, following the
specific hub revision's DIP-switch or address-strap instructions. Then set
`CONFIG_KADENCE_SENSOR_HUB_ADDRESS=0x71` in ESP-IDF menuconfig under **Kadence
sensor bus** and rebuild. The compiled default remains `0x70` for the factory
empty-hub test. Changing software alone does not change the physical address.
Never auto-select a hub by writing control bytes to all addresses `0x70..0x77`.

UnitV is deliberately untouched. Verify the delivered model and installed
firmware/transport before its integration; no guessed UART/USB/vision contract
is introduced here.

## Validation completed locally

- Runtime setup check: PASS.
- Python suite: 103 passed, 2 skipped (optional desktop/platform checks), 41 subtests passed.
- Phase B, checkpoint23, Phase A4, voice cancel, self-init and voice-wire gates: PASS.
- Native input-feedback, voice-socket and control-frame interaction tests: PASS.
- Native sensor bus and sensor protocol tests: PASS.
- AddressSanitizer and UndefinedBehaviorSanitizer enabled. Local LeakSanitizer
  disabled because this container cannot inspect process task directories; CI
  retains the normal full sanitizer settings.

CI also runs these tests, builds with ESP-IDF 5.5.4, checks the linked startup
stack budget, and packages the matching firmware and Windows app. Check the
**Rebuild body firmware** run for this source revision before using its artifact.
Local native tests do not establish the real firmware build or physical results.

## Physical check — first no hub, then empty hub

1. Use `C:\KadenceX\source` on `kadence/sensor-clean-base`; pull with
   `git pull --ff-only`. Use the successful CI candidate firmware, or build with
   `powershell -ExecutionPolicy Bypass -File .\rebuild\tools\build_firmware.ps1`
   from an ESP-IDF 5.5.4 setup. Keep the tested fallback firmware package.
2. Close Signal Console completely (including its tray icon) and close serial
   monitors. Flash the packaged firmware with its existing `flash.ps1 -Port COM4`.
   Restart normally if the device stays in download mode. No flash erase is needed.
3. Leave all new modules disconnected. Confirm stable boot/avatar. Start Signal
   Console and check repeated touch-started voice turns, cue, touch cancellation,
   a following successful reply, app volume, a reminder and camera snapshot.
   Retain the previously known top-swipe-volume limitation; do not expand scope.
4. Close Signal Console again, then run this from the source folder:

   ```powershell
   py -3.12 .\rebuild\tools\sensor_status.py --port COM4 --watch 3
   ```

   Expect a fresh `absent` hub and six unavailable channels. A `fault` instead
   points to a bus/wiring/pull-up problem. The command only reads diagnostics;
   it does not run the voice service. Do not open two COM owners together.
5. Power off. Connect only the empty hub's upstream connection to Port A; leave
   channels 0..5 empty and use its factory `0x70` address. Power on. Repeat the
   diagnostic. Within two samples expect fresh `ready`, six `ready` channels and
   no responding downstream addresses. `upstream_mask` includes bit 4 because
   the hub itself is `0x70`; the diagnostic omits the hub from upstream devices.
6. Close the diagnostic and repeat the voice/cancel/volume/reminder/camera checks
   in Signal Console with the empty hub attached. Check for resets or audible
   regressions. Then power off, remove the hub and confirm normal operation again.

Record pass/fail and logs for no-hub boot/voice, empty-hub detection, empty-hub
voice/cancel, camera, reminders and app volume. **Physical sign-off is pending.**
Only after those pass: verify ENV identity, resolve the hub address and begin
the ENV driver as the next separate milestone.

## Primary references

- [M5Stack CoreS3 pin map](https://docs.m5stack.com/en/core/CoreS3)
- [M5Stack PCA9548AP driver and six-channel contract](https://github.com/m5stack/M5Unit-HUB/blob/main/src/unit/unit_PCA9548AP.hpp)
- [NXP PCA9548A datasheet, sections 6.1–6.4](https://www.nxp.com/docs/en/data-sheet/PCA9548A.pdf)
- [Espressif I2C API, ESP-IDF 5.5.4](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/api-reference/peripherals/i2c.html)
- [M5Stack ENV III and generation comparison](https://docs.m5stack.com/en/unit/envIII)
