#pragma once

#include <algorithm>
#include <cstdint>

#include <hal/hal.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

namespace kadence_motion {

constexpr const char* kLogTag = "KADENCE-MOTION";

// Factory/Open-Source StackChan coordinate model:
//   yaw   = signed tenths of a degree around centre.
//   pitch = positive tenths of a degree, with larger values looking upward.
// The official HAL configures pitch to 30..870 and yaw to -1280..1280.
// Project Kadence deliberately uses a smaller conservative yaw envelope while
// preserving the official pitch coordinate system exactly.
constexpr int kSafeYawMinimum = -320;
constexpr int kSafeYawMaximum = 320;
constexpr int kSafePitchMinimum = 30;
constexpr int kSafePitchMaximum = 870;
constexpr int kMinimumMoveSpeed = 120;
constexpr int kMaximumMoveSpeed = 850;
constexpr int kHomeSpeed = 650;
constexpr int kPositionTolerance = 40;
constexpr uint32_t kMoveTimeoutMs = 4500;
constexpr uint32_t kHomeTimeoutMs = 7000;

// Runtime rest pose only; stored zero calibration is never modified.
constexpr int kRestYaw = 80;      // 8 degrees right.
constexpr int kRestPitch = 300;   // 30 degrees upward in the official pitch model.

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

inline int absolute_difference(int first, int second)
{
    const int difference = first - second;
    return difference < 0 ? -difference : difference;
}

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
            return {kRestYaw, 500};
        case MotionPreset::LookDown:
            return {kRestYaw, 100};
        case MotionPreset::DiagonalUpperLeft:
            return {-60, 420};
        case MotionPreset::DiagonalUpperRight:
            return {220, 420};
        case MotionPreset::DiagonalLowerLeft:
            return {-60, 180};
        case MotionPreset::DiagonalLowerRight:
            return {220, 180};
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

inline void restore_factory_idle_policy(stackchan::motion::Motion& motion)
{
    auto& yaw = motion.yawServo();
    auto& pitch = motion.pitchServo();

    yaw.setAutoAngleSyncEnabled(true);
    pitch.setAutoAngleSyncEnabled(true);
    yaw.setAutoTorqueReleaseEnabled(true);
    pitch.setAutoTorqueReleaseEnabled(true);
    release_all_torque(motion);
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
    motion.stop();
    motion.update();
    restore_factory_idle_policy(motion);
}

inline bool readback_matches(const SafeTarget& target, const SafeTarget& actual)
{
    return absolute_difference(target.yaw, actual.yaw) <= kPositionTolerance &&
           absolute_difference(target.pitch, actual.pitch) <= kPositionTolerance;
}

inline bool move_safe(int yaw, int pitch, int speed, bool release_torque = true)
{
    auto& motion = GetStackChan().motion();
    const SafeTarget safe = clamp_target(yaw, pitch);
    const int safe_speed = clamp_speed(speed);

    if (safe.yaw != yaw || safe.pitch != pitch) {
        mclog::tagWarn(kLogTag,
                       "factory-coordinate target clamped from [{},{}] to [{},{}]",
                       yaw,
                       pitch,
                       safe.yaw,
                       safe.pitch);
    }

    prepare_controlled_move(motion);
    motion.moveWithSpeed(safe.yaw, safe.pitch, safe_speed);

    if (!wait_for_stop(motion, kMoveTimeoutMs)) {
        mclog::tagError(kLogTag,
                        "movement to factory-coordinate target [{},{}] timed out",
                        safe.yaw,
                        safe.pitch);
        stop_and_release(motion);
        return false;
    }

    const auto current = motion.getCurrentAngles();
    const SafeTarget actual{current.x, current.y};
    mclog::tagInfo(kLogTag,
                   "movement read-back: requested [{},{}], actual [{},{}], speed {}",
                   safe.yaw,
                   safe.pitch,
                   actual.yaw,
                   actual.pitch,
                   safe_speed);

    if (!readback_matches(safe, actual)) {
        mclog::tagError(kLogTag,
                        "movement read-back outside tolerance: requested [{},{}], actual [{},{}], tolerance {}",
                        safe.yaw,
                        safe.pitch,
                        actual.yaw,
                        actual.pitch,
                        kPositionTolerance);
        stop_and_release(motion);
        return false;
    }

    if (release_torque) {
        restore_factory_idle_policy(motion);
    }

    return true;
}

inline bool move_preset(MotionPreset preset, int speed = 650, bool release_torque = true)
{
    const SafeTarget target = preset_target(preset);
    return move_safe(target.yaw, target.pitch, speed, release_torque);
}

inline bool go_to_calibrated_home()
{
    auto& motion = GetStackChan().motion();

    // Use the stored official zero calibration. The factory HAL itself clamps
    // pitch 0 to its configured physical minimum (normally 30). Never call
    // setCurrentAngleAsZero() or resetZeroCalibration() automatically.
    restore_factory_idle_policy(motion);
    GetHAL().delay(500);
    prepare_controlled_move(motion);

    motion.goHome(kHomeSpeed);
    mclog::tagInfo(kLogTag, "requesting official stored home [0,0]");

    if (!wait_for_stop(motion, kHomeTimeoutMs)) {
        mclog::tagError(kLogTag,
                        "home movement timed out; stopping and releasing torque");
        stop_and_release(motion);
        return false;
    }

    const auto current = motion.getCurrentAngles();
    mclog::tagInfo(kLogTag,
                   "official home read-back [{},{}]; pitch reflects factory HAL minimum",
                   current.x,
                   current.y);
    restore_factory_idle_policy(motion);
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
