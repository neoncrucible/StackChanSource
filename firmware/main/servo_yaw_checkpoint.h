#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kStepPauseMs = 170;
constexpr uint32_t kBehaviourPauseMs = 700;

inline bool run_target(int yaw_offset,
                       int pitch_offset,
                       int speed,
                       uint32_t hold_ms,
                       const char* label)
{
    const kadence_motion::SafeTarget target =
        kadence_motion::offset_from_rest(yaw_offset, pitch_offset);

    mclog::tagInfo(kLogTag,
                   "proven movement step: {} offset=[{},{}] target=[{},{}] speed={}",
                   label,
                   yaw_offset,
                   pitch_offset,
                   target.yaw,
                   target.pitch,
                   speed);

    if (!kadence_motion::move_safe(target.yaw, target.pitch, speed, true)) {
        mclog::tagError(kLogTag, "movement failed safely: {}", label);
        return false;
    }

    GetHAL().delay(hold_ms);
    return true;
}

inline bool run_nod()
{
    return run_target(0, 0, 320, kStepPauseMs, "nod rest") &&
           run_target(0, 140, 300, kStepPauseMs, "nod down") &&
           run_target(0, -50, 300, kStepPauseMs, "nod up") &&
           run_target(0, 120, 300, kStepPauseMs, "nod down return") &&
           run_target(0, 0, 320, 260, "nod rest finish");
}

inline bool run_shake()
{
    return run_target(0, 0, 320, kStepPauseMs, "shake rest") &&
           run_target(-150, 0, 320, 150, "shake left") &&
           run_target(150, 0, 320, 150, "shake right") &&
           run_target(-120, 0, 320, 150, "shake left return") &&
           run_target(0, 0, 320, 260, "shake rest finish");
}

inline bool run_scan()
{
    return run_target(0, 0, 280, 220, "scan rest") &&
           run_target(-220, -30, 240, 260, "scan upper-left") &&
           run_target(0, 90, 240, 220, "scan centre-low") &&
           run_target(220, -30, 240, 260, "scan upper-right") &&
           run_target(0, 0, 280, 300, "scan rest finish");
}

// Regression-fix checkpoint:
//   startup -> colour sweep -> LEDs off -> calibrated zero -> adjusted rest
//   -> nod -> shake -> scan -> adjusted rest -> torque off
//
// Each pose now uses the exact blocking move_safe() execution path that passed
// the signed-off two-axis hardware checkpoint. Stored calibration is untouched.
inline void run_once()
{
    kadence_startup::run();
    mclog::tagInfo(kLogTag, "starting proven-path motion regression fix");
    kadence_motion::log_servo_diagnostics();

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "initial calibrated home failed; checkpoint aborted safely");
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!kadence_motion::go_to_rest_pose()) {
        mclog::tagError(kLogTag, "adjusted rest pose failed; checkpoint aborted safely");
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_nod()) {
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_shake()) {
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_scan()) {
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!kadence_motion::go_to_rest_pose()) {
        mclog::tagError(kLogTag, "final rest pose failed; checkpoint ended safely");
        return;
    }

    kadence_startup::hard_blackout_rgb_arrays();
    kadence_motion::log_servo_diagnostics();
    mclog::tagInfo(kLogTag,
                   "proven-path checkpoint complete at rest; LEDs off and torque released");
}

}  // namespace kade_servo_checkpoint
