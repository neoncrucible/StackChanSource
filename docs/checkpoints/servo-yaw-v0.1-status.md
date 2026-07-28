# Servo yaw v0.1 status

- Branch created from the verified Kade Eye milestone.
- Safety sequence documented.
- Controlled yaw helper implemented with a 2-degree offset, low speed, watchdog feeding, movement timeouts and torque release.
- Helper is explicitly integrated into the Kade Eye runtime as a one-shot FreeRTOS task.
- Eye rendering and boot audio continue in their existing runtime paths.
- Dedicated ESP-IDF 5.5.4 CI workflow added for this branch.
- Do not flash until CI is green and the packaged artifact manifests and checksums have been inspected.
