#pragma once

#include <mooncake_log.h>
#include <hal/hal.h>
#include <stackchan/stackchan.h>

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr int kYawOffsetUnits = 100;  // 10 degrees; motion API uses tenths of a degree.
constexpr int kMoveSpeed = 500;       // Matches the proven factory servo-test speed.
constexpr uint32_t kSettleDelayMs = 1500;
constexpr uint32_t kMoveTimeoutMs = 4000;
constexpr uint32_t kHoldMs = 750;

inline bool wait_for_yaw_stop(stackchan::motion::Motion& motion, uint32_t timeout_ms)
{
    auto& yaw = motion.yawServo();
    const uint32_t deadline = GetHAL().millis() + timeout_ms;

    while (yaw.isMoving()) {
        // Servo movement is animation-driven. The factory runtime calls Motion::update()
        // continuously; without this call the target changes but no physical command is sent.
        motion.update();

        if (static_cast<int32_t>(GetHAL().millis() - deadline) >= 0) {
            return false;
        }
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }

    // Allow the final snap-to-target update to be applied before torque release.
    motion.update();
    return true;
}

inline void release_yaw_torque(stackchan::motion::Motion& motion)
{
    motion.yawServo().setTorqueEnabled(false);
    motion.pitchServo().setTorqueEnabled(false);
}

inline void run_once()
{
    auto& motion = GetStackChan().motion();
    auto& yaw = motion.yawServo();
    auto& pitch = motion.pitchServo();

    // Mirror the factory servo-test behaviour that synchronises the animation start
    // from physical feedback, but control torque per axis so pitch remains untouched.
    yaw.setAutoAngleSyncEnabled(true);
    yaw.setAutoTorqueReleaseEnabled(false);
    pitch.setAutoTorqueReleaseEnabled(false);
    release_yaw_torque(motion);

    GetHAL().delay(kSettleDelayMs);

    const int start_yaw = yaw.getCurrentAngle();
    const auto limits = yaw.getAngleLimit();
    int target_yaw = start_yaw + kYawOffsetUnits;
    if (target_yaw > limits.y) {
        target_yaw = start_yaw - kYawOffsetUnits;
    }
    if (target_yaw < limits.x || target_yaw > limits.y) {
        mclog::tagError(kLogTag, "no safe yaw target from start={} limits=[{},{}]", start_yaw, limits.x, limits.y);
        release_yaw_torque(motion);
        return;
    }

    mclog::tagInfo(kLogTag, "captured yaw={}, target={}", start_yaw, target_yaw);

    yaw.setTorqueEnabled(true);
    yaw.moveWithSpeed(target_yaw, kMoveSpeed);

    if (!wait_for_yaw_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag, "outbound yaw move timed out; holding current yaw and releasing torque");
        yaw.move(yaw.getCurrentAngle());
        motion.update();
        release_yaw_torque(motion);
        return;
    }

    GetHAL().delay(kHoldMs);
    yaw.moveWithSpeed(start_yaw, kMoveSpeed);

    if (!wait_for_yaw_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag, "return yaw move timed out; holding current yaw and releasing torque");
        yaw.move(yaw.getCurrentAngle());
        motion.update();
        release_yaw_torque(motion);
        return;
    }

    yaw.move(yaw.getCurrentAngle());
    motion.update();
    release_yaw_torque(motion);
    mclog::tagInfo(kLogTag, "yaw checkpoint complete; torque released");
}

}  // namespace kade_servo_checkpoint
