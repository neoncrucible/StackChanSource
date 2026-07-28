#pragma once

#include <mooncake_log.h>
#include <hal/hal.h>
#include <stackchan/stackchan.h>

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr int kYawOffsetUnits = 20;   // 2 degrees; motion API uses tenths of a degree.
constexpr int kMoveSpeed = 100;       // API range: 0-1000.
constexpr uint32_t kSettleDelayMs = 1500;
constexpr uint32_t kMoveTimeoutMs = 4000;
constexpr uint32_t kHoldMs = 750;

inline bool wait_for_yaw_stop(stackchan::motion::Motion& motion, uint32_t timeout_ms)
{
    const uint32_t deadline = GetHAL().millis() + timeout_ms;
    while (motion.isYawMoving()) {
        if (static_cast<int32_t>(GetHAL().millis() - deadline) >= 0) {
            return false;
        }
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }
    return true;
}

inline void run_once()
{
    auto& motion = GetStackChan().motion();

    motion.setAutoAngleSyncEnabled(false);
    motion.setAutoTorqueReleaseEnabled(false);
    motion.setTorqueEnabled(false);

    GetHAL().delay(kSettleDelayMs);

    const int start_yaw = motion.getCurrentYawAngle();
    const int target_yaw = start_yaw + kYawOffsetUnits;
    mclog::tagInfo(kLogTag, "captured yaw={}, target={}", start_yaw, target_yaw);

    motion.setTorqueEnabled(true);
    motion.moveYaw(target_yaw, kMoveSpeed);

    if (!wait_for_yaw_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag, "outbound yaw move timed out; stopping and releasing torque");
        motion.stop();
        motion.setTorqueEnabled(false);
        return;
    }

    GetHAL().delay(kHoldMs);
    motion.moveYaw(start_yaw, kMoveSpeed);

    if (!wait_for_yaw_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag, "return yaw move timed out; stopping and releasing torque");
        motion.stop();
        motion.setTorqueEnabled(false);
        return;
    }

    motion.stop();
    motion.setTorqueEnabled(false);
    mclog::tagInfo(kLogTag, "yaw checkpoint complete; torque released");
}

}  // namespace kade_servo_checkpoint
