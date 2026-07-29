#pragma once

#include <hal/hal.h>
#include <mooncake_log.h>

#include "kadence_motion_controller.h"
#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";
constexpr uint32_t kLoopDelayMs = 20;
constexpr uint32_t kBehaviourPauseMs = 700;

inline bool run_behaviour(kadence_motion_controller::Controller& controller,
                          kadence_motion_controller::Behaviour behaviour,
                          const char* label)
{
    mclog::tagInfo(kLogTag, "starting non-blocking behaviour: {}", label);

    if (!controller.start(behaviour)) {
        mclog::tagError(kLogTag, "could not start behaviour: {}", label);
        return false;
    }

    while (controller.isBusy()) {
        controller.update();
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(kLoopDelayMs);
    }

    if (controller.hasFailed()) {
        mclog::tagError(kLogTag, "behaviour failed safely: {}", label);
        return false;
    }

    mclog::tagInfo(kLogTag, "behaviour complete: {}", label);
    GetHAL().delay(kBehaviourPauseMs);
    return true;
}

// Non-blocking motion-controller hardware checkpoint:
//   startup -> calibrated home -> nod -> shake -> scan -> calibrated home
//
// Controller::update() advances each behaviour incrementally, allowing the main
// StackChan update, watchdog and other runtime work to continue between servo
// commands. All targets remain inside the already proven yaw/pitch envelope.
inline void run_once()
{
    kadence_startup::run();
    mclog::tagInfo(kLogTag, "starting Alpha 1 non-blocking motion checkpoint");
    kadence_motion::log_servo_diagnostics();

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "initial calibrated home failed; checkpoint aborted safely");
        return;
    }
    GetHAL().delay(kBehaviourPauseMs);

    kadence_motion_controller::Controller controller;

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Nod,
                       "nod")) {
        return;
    }

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Shake,
                       "shake")) {
        return;
    }

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Scan,
                       "scan")) {
        return;
    }

    if (!kadence_motion::go_to_calibrated_home()) {
        mclog::tagError(kLogTag, "final calibrated home failed; checkpoint ended safely");
        return;
    }

    kadence_motion::log_servo_diagnostics();
    mclog::tagInfo(kLogTag,
                   "Alpha 1 non-blocking motion checkpoint complete; torque released");
}

}  // namespace kade_servo_checkpoint
