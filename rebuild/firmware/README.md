# Clean body firmware

This is a standalone ESP-IDF 5.5.4 project for the rebuilt physical endpoint.
It does not compile or link the legacy Kadence application, Xiaozhi runtime, LLM logic, Wi-Fi stack, audio pipeline, avatar UI, or motion controller.

## Probe 0 — inert body

Signed off on physical CoreS3 hardware:

- stable ESP32-S3 boot;
- reset/reconnect survives the board's manual-reset USB behaviour;
- five-second heartbeat;
- stable free heap across repeated boots;
- no motion, audio, display or network driver.

## Probe 1 — display ownership

Adds only the minimum physically proven CoreS3 display path:

- I2C1 on SDA 12 / SCL 11;
- AXP2101 display/backlight rail setup;
- AW9523 panel reset path;
- SPI3 on MOSI 37 / SCLK 36, CS 3, DC 35;
- ILI9341-compatible panel driver at 40 MHz;
- direct four-band RGB565 test frame;
- backlight enabled only after the complete frame is drawn.

LVGL, touch, audio, servos, Wi-Fi and personality/presentation layers remain disabled. Stored servo zero calibration is never touched.

## Build

From an ESP-IDF 5.5.4 shell:

```powershell
cd rebuild\firmware
idf.py build
```

Do not flash a build that did not pass the dedicated rebuild firmware CI gate.
