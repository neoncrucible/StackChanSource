#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kStepPauseMs = 120;
constexpr uint32_t kBehaviourPauseMs = 500;
constexpr int kFastTestSpeed = 700;
constexpr int kScanTestSpeed = 650;

inline bool run_target(int yaw,
                       int pitch,
                       int speed,
                       uint32_t hold_ms,
                       const char* label)
{
    mclog::tagInfo(kLogTag,
                   "factory-coordinate movement step: {} target=[{},{}] speed={}",
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
    // Official pitch model: larger positive values look upward.
    return run_target(80, 300, kFastTestSpeed, kStepPauseMs, "nod rest") &&
           run_target(80, 100, kFastTestSpeed, kStepPauseMs, "nod down") &&
           run_target(80, 500, kFastTestSpeed, kStepPauseMs, "nod up") &&
           run_target(80, 100, kFastTestSpeed, kStepPauseMs, "nod down return") &&
           run_target(80, 300, kFastTestSpeed, 220, "nod rest finish");
}

inline bool run_shake()
{
    return run_target(80, 300, kFastTestSpeed, kStepPauseMs, "shake rest") &&
           run_target(-100, 300, kFastTestSpeed, 120, "shake left") &&
           run_target(260, 300, kFastTestSpeed, 120, "shake right") &&
           run_target(-70, 300, kFastTestSpeed, 120, "shake left return") &&
           run_target(80, 300, kFastTestSpeed, 220, "shake rest finish");
}

inline bool run_scan()
{
    return run_target(80, 300, kScanTestSpeed, 180, "scan rest") &&
           run_target(-140, 420, kScanTestSpeed, 220, "scan upper-left") &&
           run_target(80, 180, kScanTestSpeed, 180, "scan centre-low") &&
           run_target(300, 420, kScanTestSpeed, 220, "scan upper-right") &&
           run_target(80, 300, kScanTestSpeed, 260, "scan rest finish");
}

[[noreturn]] inline void enter_safe_idle_update_loop(bool test_passed)
{
    auto& motion = GetStackChan().motion();
    kadence_motion::restore_factory_idle_policy(motion);
    kadence_startup::hard_blackout_rgb_arrays();
    kadence_motion::log_servo_diagnostics();

    if (test_passed) {
        mclog::tagInfo(kLogTag,
                       "factory-coordinate checkpoint complete; torque released and continuous updates active");
    } else {
        mclog::tagError(kLogTag,
                        "factory-coordinate checkpoint aborted safely; torque released and continuous updates active");
    }

    // Match the official firmware lifecycle: keep StackChan motion and automatic
    // torque-release servicing alive at 50 Hz after the one-shot checkpoint.
    while (true) {
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }
}

// Final factory-coordinate checkpoint:
//   startup -> colour sweep -> LEDs off -> official stored home
//   -> rest [80,300] -> fast nod [100..500 pitch]
//   -> fast shake -> diagonal scan -> rest -> torque off
//   -> continuous official-style StackChan update loop
//
// Pitch coordinates and direction are taken directly from the open-source
// factory firmware: valid pitch 30..870, with larger values looking upward.
inline void run_once()
{
    kadence_startup::run();
    mclog::tagInfo(kLogTag, "starting final factory-coordinate motion test");
    kadence_motion::log_servo_diagnostics();

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "initial calibrated home failed");
        enter_safe_idle_update_loop(false);
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!kadence_motion::go_to_rest_pose()) {
        mclog::tagError(kLogTag, "factory-coordinate rest pose failed");
        enter_safe_idle_update_loop(false);
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_nod()) {
        enter_safe_idle_update_loop(false);
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_shake()) {
        enter_safe_idle_update_loop(false);
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!run_scan()) {
        enter_safe_idle_update_loop(false);
    }
    GetHAL().delay(kBehaviourPauseMs);

    if (!kadence_motion::go_to_rest_pose()) {
        mclog::tagError(kLogTag, "final rest pose failed");
        enter_safe_idle_update_loop(false);
    }

    enter_safe_idle_update_loop(true);
}

}  // namespace kade_servo_checkpoint
