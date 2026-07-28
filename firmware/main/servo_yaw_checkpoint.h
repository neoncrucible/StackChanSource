#pragma once

#include <mooncake_log.h>

#include "kadence_startup.h"
#include "safe_motion_foundation.h"

namespace kade_servo_checkpoint {

constexpr const char* kLogTag = "KADE-SERVO";

// Compatibility entry point retained for the existing startup task. Alpha 1 now
// runs the Project Kadence splash/RGB sequence and then moves to the official
// stored calibrated home. No boot-time zero calibration is written.
inline void run_once()
{
    kadence_startup::run();

    mclog::tagInfo(kLogTag, "starting Alpha 1 calibrated-home checkpoint");
    const bool reached_home = kadence_motion::go_to_calibrated_home();
    if (reached_home) {
        mclog::tagInfo(kLogTag, "Alpha 1 calibrated-home checkpoint complete");
    } else {
        mclog::tagError(kLogTag, "Alpha 1 calibrated-home checkpoint failed safely");
    }
}

}  // namespace kade_servo_checkpoint
