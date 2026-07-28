# Build gate

No artifact from this branch is approved for flashing until all of the following are true:

- the yaw helper is explicitly integrated into the runtime
- the branch workflow completes successfully
- the artifact digest is recorded
- every packaged file passes SHA-256 verification
- `flash_args` and `flasher_args.json` agree
- the test operator confirms the robot can be disconnected from power immediately
