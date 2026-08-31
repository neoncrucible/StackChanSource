# Clean body firmware

This is a standalone ESP-IDF 5.5.4 project for the rebuilt physical endpoint.
It does not compile or link the legacy Kadence application, Xiaozhi runtime, LLM logic, Wi-Fi stack, audio pipeline, display UI, or motion controller.

## Probe 0

The first hardware image is deliberately inert. It only:

- boots the ESP32-S3;
- derives a stable device ID from the factory MAC;
- reports the reset reason;
- prints the frozen body contract and hardware safety policy;
- emits a five-second heartbeat with uptime and free heap.

Motion, audio, display and network drivers remain disabled. Stored servo zero calibration is never touched.

## Build

From an ESP-IDF 5.5.4 shell:

```powershell
cd rebuild\firmware
idf.py build
```

Do not flash a build that did not pass the dedicated rebuild firmware CI gate.
