#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kStepPauseMs = 170;
constexpr uint32_t kBehaviourPauseMs = 700;

inline bool run_target(int yaw,
                       int pitch,
                       int speed,
                       uint32_t hold_ms,
                       const char* label)
{
    mclog::tagInfo(kLogTag,
                   "signed-off movement step: {} target=[{},{}] speed={}",
                   label,
                   yaw,
                   pitch,
                   speed);

    if (!kadence_motion::move_safe(yaw, pitch, speed, true)) {
        mclog::tagError(kLogTag, "movement failed safely: {}", label);
        return false;
    }

    GetHAL().delay(hold_ms);
    return true;
}

inline bool run_nod()
{
    // Pitch uses only the exact physically approved absolute range: -80..+80.
    return run_target(80, -40, 320, kStepPauseMs, "nod rest") &&
           run_target(80, 80, 300, kStepPauseMs, "nod down") &&
           run_target(80, -80, 300, kStepPauseMs, "nod up") &&
           run_target(80, 60, 300, kStepPauseMs, "nod down return") &&
           run_target(80, -40, 320, 260, "nod rest finish");
}

inline bool run_shake()
{
    return run_target(80, -40, 320, kStepPauseMs, "shake rest") &&
           run_target(-70, -40, 320, 150, "shake left") &&
           run_target(230, -40, 320, 150, "shake right") &&
           run_target(-40, -40, 320, 150, "shake left return") &&
           run_target(80, -40, 320, 260, "shake rest finish");
}

inline bool run_scan()
{
    return run_target(80, -40, 280, 220, "scan rest") &&
           run_target(-140, -70, 240, 260, "scan upper-left") &&
           run_target(80, 40, 240, 220, "scan centre-low") &&
           run_target(300, -70, 240, 260, "scan upper-right") &&
           run_target(80, -40, 280, 300, "scan rest finish");
}

// Signed-off-envelope checkpoint:
//   startup -> colour sweep -> LEDs off -> calibrated zero -> adjusted rest
//   -> nod -> shake -> scan -> adjusted rest -> torque off
//
// Every vertical target is an absolute calibrated value inside the exact range
// that passed the earlier two-axis hardware test: -80, 0 and +80, with the
// resting and scan poses kept between those limits. Stored calibration is untouched.
inline void run_once()
{
    kadence_startup::run();
    mclog::tagInfo(kLogTag, "starting signed-off-envelope motion revision");
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
                   "signed-off-envelope checkpoint complete at rest; LEDs off and torque released");
}

}  // namespace kade_servo_checkpoint
