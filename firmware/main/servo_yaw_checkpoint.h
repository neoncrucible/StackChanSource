#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kCheckpointPauseMs = 650;

inline bool run_yaw_checkpoint_step(kadence_motion::MotionPreset preset,
                                    const char* label,
                                    int speed = 280)
{
    mclog::tagInfo(kLogTag, "servo checkpoint step: {}", label);
    const bool ok = kadence_motion::move_preset(preset, speed, true);
    GetHAL().delay(kCheckpointPauseMs);
    return ok;
}

// Hardware checkpoint sequence:
//   calibrated home -> small left glance -> home -> small right glance -> home
//
// Pitch remains at calibrated zero throughout this first movement test. Every
// step is bounded, waits for completion, releases torque and aborts safely if a
// timeout occurs. No zero calibration is written.
inline void run_once()
{
    kadence_startup::run();

    mclog::tagInfo(kLogTag, "starting Alpha 1 yaw movement checkpoint");

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "initial calibrated home failed; checkpoint aborted safely");
        return;
    }
    GetHAL().delay(kCheckpointPauseMs);

    if (!run_yaw_checkpoint_step(kadence_motion::MotionPreset::GlanceLeft,
                                 "small left glance")) {
        mclog::tagError(kLogTag, "left glance failed; checkpoint aborted safely");
        return;
    }

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "home after left glance failed; checkpoint aborted safely");
        return;
    }
    GetHAL().delay(kCheckpointPauseMs);

    if (!run_yaw_checkpoint_step(kadence_motion::MotionPreset::GlanceRight,
                                 "small right glance")) {
        mclog::tagError(kLogTag, "right glance failed; checkpoint aborted safely");
        return;
    }

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "final calibrated home failed; checkpoint ended safely");
        return;
    }

    mclog::tagInfo(kLogTag,
                   "Alpha 1 yaw movement checkpoint complete; final torque released");
}

}  // namespace kade_servo_checkpoint
