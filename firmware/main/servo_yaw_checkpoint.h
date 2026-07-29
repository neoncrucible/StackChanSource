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

// Revised non-blocking hardware checkpoint:
//   startup signature -> full-colour sweep -> LEDs off -> calibrated zero
//   -> offset Project Kadence rest -> nod -> shake -> scan -> rest -> torque off
//
// Stored servo calibration remains untouched. Behaviour coordinates are runtime
// offsets around rest [8 degrees right, 10 degrees up], providing more downward
// room for the nod. LED animations are explicitly stopped before raw blackout.
inline void run_once()
{
    kadence_startup::run();
    mclog::tagInfo(kLogTag, "starting revised Alpha 1 motion and LED checkpoint");
    kadence_motion::log_servo_diagnostics();

    // Visit factory zero first so the adjusted rest pose is measured from the
    // same known calibration on every boot.
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

    kadence_motion_controller::Controller controller;

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Nod,
                       "nod with increased downward travel")) {
        return;
    }

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Shake,
                       "shake around adjusted rest")) {
        return;
    }

    if (!run_behaviour(controller,
                       kadence_motion_controller::Behaviour::Scan,
                       "scan around adjusted rest")) {
        return;
    }

    if (!kadence_motion::go_to_rest_pose()) {
        mclog::tagError(kLogTag, "final rest pose failed; checkpoint ended safely");
        return;
    }

    kadence_startup::hard_blackout_rgb_arrays();
    kadence_motion::log_servo_diagnostics();
    mclog::tagInfo(kLogTag,
                   "revised Alpha 1 checkpoint complete at rest; LEDs off and torque released");
}

}  // namespace kade_servo_checkpoint
