# Integrated servo runtime

The yaw checkpoint is launched once from the verified Kade Eye runtime after HAL, display and audio setup. It runs in a dedicated FreeRTOS task so the eye loop and watchdog maintenance remain active.

The test captures the current yaw angle, moves by 20 servo units at speed 100, returns to the captured angle, stops and releases torque. Pitch receives no position command. Any movement timeout stops the motion and releases torque.
