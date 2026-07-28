## Goal

Add the first deliberately limited servo-control checkpoint on top of the verified Kade Eye stationary runtime.

## Controlled movement

- preserve the full-screen optic eye, blink timing and boot sound
- start from torque released
- capture the current yaw angle after a 1.5 second settle period
- enable torque immediately before movement
- move yaw by 20 servo units (2 degrees) at speed 100/1000
- return to the captured starting yaw
- stop and release torque
- run once per boot
- issue no pitch position command

## Failure behaviour

- outbound and return movements have hard four-second timeouts
- timeout path stops movement and releases torque
- watchdog feeding remains active during movement waits
- eye runtime continues in the main task

## Hardware gate

This PR remains draft until CI produces the `stackchan-servo-yaw-checkpoint` artifact and its checksums and flash manifests have been inspected. Hardware testing must be performed with immediate access to power disconnect.
