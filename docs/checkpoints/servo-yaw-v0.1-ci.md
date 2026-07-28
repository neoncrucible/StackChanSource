# Servo yaw CI gate

Expected workflow: `Servo yaw checkpoint build`

Expected artifact: `stackchan-servo-yaw-checkpoint`

The artifact is not approved for flashing until the workflow is green, the archive digest is recorded, all files pass `SHA256SUMS`, and `flash_args` agrees with `flasher_args.json`.
