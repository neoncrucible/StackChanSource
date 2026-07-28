# Servo yaw checkpoint v0.1

## Goal

Prove one controlled yaw-axis movement while preserving the verified Kade Eye display, blink runtime and boot sound.

## Hardware test sequence

1. Initialise the official StackChan HAL.
2. Keep automatic angle synchronisation and automatic torque release disabled.
3. Read the current yaw position after startup settles.
4. Enable torque immediately before the test.
5. Command yaw to the captured starting position plus 20 servo units (2 degrees) at speed 100/1000.
6. Wait for completion with a hard timeout.
7. Return to the captured starting position at speed 100/1000.
8. Stop motion, release torque and leave the pitch axis untouched.
9. Never repeat the sequence until the next reboot.

## Abort conditions

Disconnect power immediately for unexpected movement, binding, grinding, sustained buzzing or failure to stop. The firmware must release torque after either normal completion or timeout.

## Acceptance criteria

- Kade Eye display and blink animation remain active.
- Boot sound plays once.
- Pitch does not receive a position command.
- Yaw moves only a small amount and returns to its captured starting position.
- Torque releases after the test.
- The sequence runs once per boot and does not loop.
