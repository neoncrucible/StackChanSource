# Captured firmware crash and host recovery — 26 September 2026

The owner supplied a 0.4.7 diagnostic export at 17:05 UTC and reported a reboot
after saying “switch to extra camera”, followed by a persistent Preparing audio
state. The screenshot confirms an existing profile with 3/3 compatible samples;
its test says no enrolled identity was confirmed, not that lighting was measured.

## Observed sequence

- 17:02:24: touch starts a turn; 17:02:26: recording starts.
- 17:02:31: thinking/STT starts, immediately followed by CPU0 StoreProhibited,
  a backtrace, Rebooting, and reset code 12. The reasoning/camera tool had not run.
- 17:02:33–38: the old host turn continues reasoning/TTS and reports first audio.
- 17:02:55: device status returns idle with touch sequence reset to zero.
- Later touches show attentive without new recording/provider work. Automatic
  perception is suppressed as voice_busy. There is no serial disconnect event.

UnitV2 captures before the crash completed with producer stop confirmed. The
automatic arrival burst at 17:01:53–56 completed two frames with no stable identity.
The report cannot establish lighting quality or the I2C bus/device involved.

## Verified symbols

Physically accepted source: `7b24e0d5f0148424eb28c9b7c2d1a7c57dd113a4`.
The corresponding PR-build firmware ZIP records actual source commit
`22fc2f5cf4c8d250c8dd11b3253993ba79ad6b97`, ESP-IDF 5.5.4, firmware 0.21.6.
Original Actions run: `34995140145`; firmware artifact: `10407830568`.
Original application binary SHA256:
`03fb7567e6ff0664291b08262bd09c5f62e53a0e8c18a77497d62101915e79bc`.

Read-only symbol rebuild:
https://github.com/neoncrucible/StackChanSource/actions/runs/36258405036
Symbols artifact: `10911302909`, no new firmware distributed or flashed.
CI compared the flash executable segment against the original binary. A further
ELF-section comparison against the downloaded original verified **all executable
sections byte for byte**: 0x40374000 (1,028 bytes), 0x40374404 (99,531 bytes),
0x42000020 (760,372 bytes). The address mapping is therefore applicable to the
accepted packaged code, subject to the device still running that accepted image.

| Address | Resolved location |
| --- | --- |
| 0x4037b29c | i2c_ll_read_rxfifo, hal/esp32s3/include/hal/i2c_ll.h:703 |
| same, inlined | i2c_isr_receive_handler, esp_driver_i2c/i2c_master.c:769 |
| same, inlined | i2c_master_isr_handler_default, i2c_master.c:812 |
| 0x40376189 | shared_intr_isr, esp_hw_support/intr_alloc.c:471 |
| 0x4037743d | _xt_lowint1, xtensa/xtensa_vectors.S:1240 |
| 0x4037b403 | xt_utils_wait_for_intr / esp_cpu_wait_for_intr |
| 0x420b8879 | wifi_thread_semphr_get_wrapper, esp_wifi/esp32s3/esp_adapter.c:220 |
| 0x4037fd3f | prvIdleTask, FreeRTOS tasks.c:4350 |

This identifies the faulting I2C receive ISR, not the originating transaction.
The Wi-Fi/idle frames are interrupted context, not proof that Wi-Fi caused it.
Do not label it a camera-switch, microphone, external sensor or poor-light fault
without additional evidence. A race or invalid receive buffer is a hypothesis,
not a confirmed source-level cause. No speculative SDK/firmware patch is included.

## Host 0.4.8 containment

USB UART can survive a CPU reset. Previously the serial reader logged boot markers
but left the old command pending for up to 210 seconds. Subsequent touches and
perception remained blocked, and the UI could retain Preparing audio.

An active session now fails on Rebooting, ROM reset or a new transport-ready boot
marker. This detection is independent of the bounded diagnostic-log quota. It
only revokes work; logs never acknowledge a command or prove physical completion.
Existing supervision cancels providers/audio/connections, rejects the old token,
discards unfinished history and reconnects normally. Initial boot markers during
startup remain normal. Regression exercises a real voice socket/serial owner,
pending STT, USB remaining open, cancellation, and the next successful touch.

**Remaining:** firmware 0.21.6 can still hit the I2C interrupt fault. The host update
recovers from a reboot; it does not prevent it. Hardware acceptance should include
ordinary voice and a camera-selection voice command, plus fresh diagnostics if a
reboot recurs. Continue firmware investigation from these verified symbols and
obtain the panic register set / I2C transaction context before choosing a fix.
