#pragma once

#include <algorithm>
#include <cstdint>

#include <hal/hal.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

namespace kadence_motion {

constexpr const char* kLogTag = "KADENCE-MOTION";

// Official StackChan BSP limits are yaw [-1280, 1280] and pitch [30, 870].
// Alpha 1 deliberately stays further inside those absolute limits.
constexpr int kSafeYawMinimum = -1100;
constexpr int kSafeYawMaximum = 1100;
constexpr int kSafePitchMinimum = 100;
constexpr int kSafePitchMaximum = 800;
constexpr int kHomeSpeed = 500;
constexpr uint32_t kHomeTimeoutMs = 7000;

struct SafeTarget {
    int yaw;
    int pitch;
};

inline SafeTarget clamp_target(int yaw, int pitch)
{
    return {
        std::clamp(yaw, kSafeYawMinimum, kSafeYawMaximum),
        std::clamp(pitch, kSafePitchMinimum, kSafePitchMaximum),
    };
}

inline void release_all_torque(stackchan::motion::Motion& motion)
{
    motion.yawServo().setTorqueEnabled(false);
    motion.pitchServo().setTorqueEnabled(false);
}

inline bool wait_for_stop(stackchan::motion::Motion& motion, uint32_t timeout_ms)
{
    const uint32_t deadline = GetHAL().millis() + timeout_ms;
    while (motion.isMoving()) {
        motion.update();
        if (static_cast<int32_t>(GetHAL().millis() - deadline) >= 0) {
            return false;
        }
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }

    motion.update();
    return true;
}

inline bool move_safe(int yaw, int pitch, int speed)
{
    auto& motion = GetStackChan().motion();
    const SafeTarget safe = clamp_target(yaw, pitch);

    if (safe.yaw != yaw || safe.pitch != pitch) {
        mclog::tagWarn(kLogTag,
                       "motion target clamped from [{},{}] to [{},{}]",
                       yaw, pitch, safe.yaw, safe.pitch);
    }

    motion.moveWithSpeed(safe.yaw, safe.pitch, std::clamp(speed, 0, 1000));
    return true;
}

inline bool go_to_calibrated_home()
{
    auto& motion = GetStackChan().motion();
    auto& yaw = motion.yawServo();
    auto& pitch = motion.pitchServo();

    // Use the official stored zero calibration. Do not call setCurrentAngleAsZero()
    // or resetZeroCalibration(); Alpha 1 must never rewrite calibration at boot.
    yaw.setAutoAngleSyncEnabled(true);
    pitch.setAutoAngleSyncEnabled(true);
    yaw.setAutoTorqueReleaseEnabled(false);
    pitch.setAutoTorqueReleaseEnabled(false);

    release_all_torque(motion);
    GetHAL().delay(500);

    yaw.setTorqueEnabled(true);
    pitch.setTorqueEnabled(true);
    motion.goHome(kHomeSpeed);
    mclog::tagInfo(kLogTag, "moving to stored calibrated home [0,0]");

    if (!wait_for_stop(motion, kHomeTimeoutMs)) {
        mclog::tagError(kLogTag, "home movement timed out; holding current angles and releasing torque");
        yaw.move(yaw.getCurrentAngle());
        pitch.move(pitch.getCurrentAngle());
        motion.update();
        release_all_torque(motion);
        return false;
    }

    yaw.move(yaw.getCurrentAngle());
    pitch.move(pitch.getCurrentAngle());
    motion.update();
    release_all_torque(motion);
    mclog::tagInfo(kLogTag, "calibrated home reached; torque released");
    return true;
}

}  // namespace kadence_motion
