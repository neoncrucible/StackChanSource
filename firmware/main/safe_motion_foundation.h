#pragma once

#include <algorithm>
#include <cstdint>

#include <hal/hal.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

namespace kadence_motion {

constexpr const char* kLogTag = "KADENCE-MOTION";

// StackChan has two rotational axes only: yaw (left/right) and pitch (up/down).
// There is no roll axis, so a true head tilt/twist is physically impossible.
// Diagonal poses are simultaneous yaw and pitch commands.
//
// Motion values are tenths of a degree relative to stored calibrated home:
// [0,0] is the official factory-calibrated zero and 100 = 10 degrees.
constexpr int kSafeYawMinimum = -320;
constexpr int kSafeYawMaximum = 320;
constexpr int kSafePitchMinimum = -180;
constexpr int kSafePitchMaximum = 180;
constexpr int kMinimumMoveSpeed = 120;
constexpr int kMaximumMoveSpeed = 650;
constexpr int kHomeSpeed = 500;
constexpr uint32_t kMoveTimeoutMs = 4500;
constexpr uint32_t kHomeTimeoutMs = 7000;

// Runtime rest pose only; stored calibration is never modified.
// Pitch is deliberately kept inside the physically signed-off -80..+80 range.
constexpr int kRestYaw = 80;     // 8 degrees right.
constexpr int kRestPitch = -40;  // 4 degrees up.

struct SafeTarget {
    int yaw;
    int pitch;
};

enum class MotionPreset : uint8_t {
    Home,
    GlanceLeft,
    GlanceRight,
    LookUp,
    LookDown,
    DiagonalUpperLeft,
    DiagonalUpperRight,
    DiagonalLowerLeft,
    DiagonalLowerRight,
};

inline SafeTarget clamp_target(int yaw, int pitch)
{
    return {
        std::clamp(yaw, kSafeYawMinimum, kSafeYawMaximum),
        std::clamp(pitch, kSafePitchMinimum, kSafePitchMaximum),
    };
}

inline SafeTarget offset_from_rest(int yaw_offset, int pitch_offset)
{
    return clamp_target(kRestYaw + yaw_offset, kRestPitch + pitch_offset);
}

inline int clamp_speed(int speed)
{
    return std::clamp(speed, kMinimumMoveSpeed, kMaximumMoveSpeed);
}

inline SafeTarget preset_target(MotionPreset preset)
{
    switch (preset) {
        case MotionPreset::GlanceLeft:
            return {-100, kRestPitch};
        case MotionPreset::GlanceRight:
            return {260, kRestPitch};
        case MotionPreset::LookUp:
            return {kRestYaw, -80};
        case MotionPreset::LookDown:
            return {kRestYaw, 80};
        case MotionPreset::DiagonalUpperLeft:
            return {-60, -70};
        case MotionPreset::DiagonalUpperRight:
            return {220, -70};
        case MotionPreset::DiagonalLowerLeft:
            return {-60, 70};
        case MotionPreset::DiagonalLowerRight:
            return {220, 70};
        case MotionPreset::Home:
        default:
            return {kRestYaw, kRestPitch};
    }
}

inline void log_servo_diagnostics()
{
    auto& motion = GetStackChan().motion();
    const auto yaw_limits = motion.yawServo().getAngleLimit();
    const auto pitch_limits = motion.pitchServo().getAngleLimit();
    const auto current = motion.getCurrentAngles();

    mclog::tagInfo(kLogTag,
                   "servo diagnostics: yaw limits [{},{}], pitch limits [{},{}], current [{},{}], rest [{},{}]",
                   yaw_limits.x,
                   yaw_limits.y,
                   pitch_limits.x,
                   pitch_limits.y,
                   current.x,
                   current.y,
                   kRestYaw,
                   kRestPitch);
}

inline void release_all_torque(stackchan::motion::Motion& motion)
{
    motion.yawServo().setTorqueEnabled(false);
    motion.pitchServo().setTorqueEnabled(false);
}

inline void prepare_controlled_move(stackchan::motion::Motion& motion)
{
    auto& yaw = motion.yawServo();
    auto& pitch = motion.pitchServo();

    yaw.setAutoAngleSyncEnabled(true);
    pitch.setAutoAngleSyncEnabled(true);
    yaw.setAutoTorqueReleaseEnabled(false);
    pitch.setAutoTorqueReleaseEnabled(false);
    yaw.setTorqueEnabled(true);
    pitch.setTorqueEnabled(true);
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

inline void stop_and_release(stackchan::motion::Motion& motion)
{
    auto& yaw = motion.yawServo();
    auto& pitch = motion.pitchServo();

    yaw.move(yaw.getCurrentAngle());
    pitch.move(pitch.getCurrentAngle());
    motion.update();
    release_all_torque(motion);
}

inline bool move_safe(int yaw, int pitch, int speed, bool release_torque = true)
{
    auto& motion = GetStackChan().motion();
    const SafeTarget safe = clamp_target(yaw, pitch);
    const int safe_speed = clamp_speed(speed);

    if (safe.yaw != yaw || safe.pitch != pitch) {
        mclog::tagWarn(kLogTag,
                       "calibrated target clamped from [{},{}] to [{},{}]",
                       yaw,
                       pitch,
                       safe.yaw,
                       safe.pitch);
    }

    prepare_controlled_move(motion);
    motion.moveWithSpeed(safe.yaw, safe.pitch, safe_speed);

    if (!wait_for_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag,
                        "movement to calibrated target [{},{}] timed out",
                        safe.yaw,
                        safe.pitch);
        stop_and_release(motion);
        return false;
    }

    if (release_torque) {
        stop_and_release(motion);
    }

    mclog::tagInfo(kLogTag,
                   "calibrated target reached [{},{}] at speed {}",
                   safe.yaw,
                   safe.pitch,
                   safe_speed);
    return true;
}

inline bool move_preset(MotionPreset preset, int speed = 320, bool release_torque = true)
{
    const SafeTarget target = preset_target(preset);
    return move_safe(target.yaw, target.pitch, speed, release_torque);
}

inline bool go_to_calibrated_home()
{
    auto& motion = GetStackChan().motion();

    // Use the official stored zero calibration. Never call
    // setCurrentAngleAsZero() or resetZeroCalibration() automatically.
    release_all_torque(motion);
    GetHAL().delay(500);
    prepare_controlled_move(motion);

    motion.goHome(kHomeSpeed);
    mclog::tagInfo(kLogTag, "moving to stored calibrated home [0,0]");

    if (!wait_for_stop(motion, kHomeTimeoutMs)) {
        mclog::tagError(kLogTag,
                        "home movement timed out; holding current angles and releasing torque");
        stop_and_release(motion);
        return false;
    }

    stop_and_release(motion);
    mclog::tagInfo(kLogTag, "calibrated home reached; torque released");
    return true;
}

inline bool go_to_rest_pose()
{
    mclog::tagInfo(kLogTag,
                   "moving to Project Kadence rest pose [{},{}]",
                   kRestYaw,
                   kRestPitch);
    return move_safe(kRestYaw, kRestPitch, kHomeSpeed, true);
}

}  // namespace kadence_motion
