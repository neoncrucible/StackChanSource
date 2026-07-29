#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kCheckpointPauseMs = 650;

inline bool run_checkpoint_step(kadence_motion::MotionPreset preset,
                                const char* label,
                                int speed = 260)
{
    mclog::tagInfo(kLogTag, "servo checkpoint step: {}", label);
    const bool ok = kadence_motion::move_preset(preset, speed, true);
    GetHAL().delay(kCheckpointPauseMs);
    return ok;
}

inline bool return_home_or_abort(const char* context)
{
    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "{}; checkpoint aborted safely", context);
        return false;
    }
    GetHAL().delay(kCheckpointPauseMs);
    return true;
}

// Two-axis hardware checkpoint. StackChan supports yaw and pitch only; there is
// no roll servo, so diagonal poses are combined yaw/pitch rather than true tilt.
// Sequence:
//   home -> up -> home -> down -> home -> upper-left diagonal -> home
//        -> lower-right diagonal -> home -> torque released
//
// Targets remain deliberately small: pitch 8 degrees and diagonal 14/7 degrees.
// Every step is clamped, timeout-protected and returns to known calibrated home.
inline void run_once()
{
    kadence_startup::run();

    mclog::tagInfo(kLogTag, "starting Alpha 1 two-axis movement checkpoint");
    kadence_motion::log_servo_diagnostics();

    if (!return_home_or_abort("initial calibrated home failed")) {
        return;
    }

    if (!run_checkpoint_step(kadence_motion::MotionPreset::LookUp,
                             "look up 8 degrees")) {
        mclog::tagError(kLogTag, "up movement failed; checkpoint aborted safely");
        return;
    }
    if (!return_home_or_abort("home after up movement failed")) {
        return;
    }

    if (!run_checkpoint_step(kadence_motion::MotionPreset::LookDown,
                             "look down 8 degrees")) {
        mclog::tagError(kLogTag, "down movement failed; checkpoint aborted safely");
        return;
    }
    if (!return_home_or_abort("home after down movement failed")) {
        return;
    }

    if (!run_checkpoint_step(kadence_motion::MotionPreset::DiagonalUpperLeft,
                             "upper-left diagonal 14/7 degrees")) {
        mclog::tagError(kLogTag, "upper-left diagonal failed; checkpoint aborted safely");
        return;
    }
    if (!return_home_or_abort("home after upper-left diagonal failed")) {
        return;
    }

    if (!run_checkpoint_step(kadence_motion::MotionPreset::DiagonalLowerRight,
                             "lower-right diagonal 14/7 degrees")) {
        mclog::tagError(kLogTag, "lower-right diagonal failed; checkpoint aborted safely");
        return;
    }
    if (!return_home_or_abort("final calibrated home failed")) {
        return;
    }

    kadence_motion::log_servo_diagnostics();
    mclog::tagInfo(kLogTag,
                   "Alpha 1 two-axis movement checkpoint complete; final torque released");
}

}  // namespace kade_servo_checkpoint
