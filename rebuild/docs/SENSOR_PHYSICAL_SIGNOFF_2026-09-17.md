# Kadence sensor physical sign-off — 2026-09-17

Candidate tested: firmware 0.21.6 / commit `7b24e0d5f0148424eb28c9b7c2d1a7c57dd113a4` on branch `kadence/sensor-clean-base`.

## Result

**Physical sensor integration: PASS.**

The owner completed the combined `tof_status.py --gesture` observation and subsequent normal Kadence smoke test.

### ToF4M

- Reached `ready`, `fresh=True` and produced repeated valid millimetre readings.
- Valid samples used `raw_status=9`.
- Observed distances changed with target movement, including approximately 48 mm, 81–93 mm, 115–136 mm, 231 mm, 431–537 mm and about 1.4–1.8 m.
- Sequence advanced beyond 100 samples.
- Transport error count remained `errors=0` throughout the recorded test.
- Intermittent invalid samples (`raw_status` 4 or 7) were correctly surfaced as `valid=False` / unavailable distance and recovered without transport errors.

### Gesture

- Reached `ready`, `fresh=True` while ToF4M remained active.
- Gesture event sequence advanced during the combined test.
- Directional events were observed, including right and up, with some mixed flags during movement.
- Gesture and ToF4M therefore operated concurrently through the shared PaHub worker.

### Regression smoke test

After the sensor diagnostic, the owner restarted normal Kadence and confirmed normal operation. Camera snapshot / Vision worked. Voice initially returned the generic thinking-service fallback for multiple questions. Ollama itself and the exact `qwen3.5:4b` model were independently verified healthy, including a full Companion → Ollama → planner JSON test.

Normal voice operation was restored after moving the robot to a different USB port and restarting the robot/server. Because those actions were not isolated, **do not record a causal root cause** for the transient voice failure. The owner then reported that all normal testing worked and explicitly approved sign-off.

## Signed-off state

- PaHub / external I2C coexistence: PASS
- Gesture PAJ7620U2 directional readings: PASS
- ToF4M VL53L1X ranging: PASS
- Gesture + ToF4M shared scheduling: PASS
- Sensor transport errors in observed run: 0
- Normal voice after recovery: PASS
- Built-in camera snapshot / Vision: PASS
- Current sensor candidate physical acceptance: **SIGNED OFF**

This sign-off confirms physical integration and coexistence for the tested candidate. It does not establish the cause of the transient USB/voice anomaly and does not add gesture actions, autonomous behaviour, or sensor data to LLM context.