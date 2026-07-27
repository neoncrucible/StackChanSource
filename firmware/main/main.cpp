/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include <smooth_ui_toolkit.hpp>
#include <mooncake_log.h>
#include <hal/hal.h>
#include <stackchan/stackchan.h>
#include <lvgl.h>

using namespace smooth_ui_toolkit;

extern "C" void app_main(void)
{
    mclog::set_level(mclog::level_info);
    mclog::set_time_format(mclog::time_format_unix_milliseconds);
    mclog::tagInfo("KADE-EYE", "starting optic-eye checkpoint");

    // Use the proven factory HAL so display, audio, power and body hardware
    // are initialised exactly as they are in the official firmware.
    GetHAL().init();

    // This checkpoint is deliberately stationary. Do not issue any position
    // commands and release torque immediately after body initialisation.
    auto& motion = GetStackChan().motion();
    motion.setAutoAngleSyncEnabled(false);
    motion.setAutoTorqueReleaseEnabled(false);
    motion.setTorqueEnabled(false);

    // Temporary visual checkpoint. The embedded optic PNG state machine is
    // added in the next commit once this stripped runtime is proven by CI.
    {
        LvglLockGuard lock;
        lv_obj_t* screen = lv_screen_active();
        lv_obj_set_style_bg_color(screen, lv_color_hex(0x000000), LV_PART_MAIN);
        lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
        lv_obj_clean(screen);
    }

    mclog::tagInfo("KADE-EYE", "stationary checkpoint ready");

    while (1) {
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();
        GetHAL().delay(20);
    }
}
