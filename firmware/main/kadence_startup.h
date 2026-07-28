#pragma once

#include <hal/hal.h>
#include <lvgl.h>
#include <mooncake_log.h>
#include <smooth_ui_toolkit.hpp>
#include <stackchan/stackchan.h>

#include <array>
#include <cstdint>

namespace kadence_startup {

constexpr const char* kLogTag = "KADENCE-BOOT";
constexpr uint32_t kSplashHoldMs = 1750;
constexpr uint32_t kColourHoldMs = 220;
constexpr uint32_t kBlackoutSettleMs = 180;

inline lv_obj_t* create_project_kadence_overlay()
{
    using namespace smooth_ui_toolkit;

    LvglLockGuard lock;
    lv_obj_t* screen = lv_screen_active();

    lv_obj_t* overlay = lv_obj_create(screen);
    lv_obj_remove_flag(overlay, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(overlay, 320, 240);
    lv_obj_center(overlay);
    lv_obj_set_style_bg_color(overlay, lv_color_hex(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(overlay, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_pad_all(overlay, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(overlay, 0, LV_PART_MAIN);
    lv_obj_move_foreground(overlay);

    lv_obj_t* title = lv_label_create(overlay);
    lv_label_set_text(title, "PROJECT KADENCE");
    lv_obj_set_style_text_color(title, lv_color_hex(0xD71920), LV_PART_MAIN);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, -12);

    lv_obj_t* subtitle = lv_label_create(overlay);
    lv_label_set_text(subtitle, "ALPHA 1");
    lv_obj_set_style_text_color(subtitle, lv_color_hex(0xE8E8E8), LV_PART_MAIN);
    lv_obj_set_style_text_font(subtitle, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(subtitle, LV_ALIGN_CENTER, 0, 24);

    lv_obj_t* line = lv_obj_create(overlay);
    lv_obj_remove_flag(line, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(line, 190, 2);
    lv_obj_set_style_bg_color(line, lv_color_hex(0xD71920), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(line, 0, LV_PART_MAIN);
    lv_obj_align(line, LV_ALIGN_CENTER, 0, 49);

    lv_obj_invalidate(overlay);
    mclog::tagInfo(kLogTag, "Project Kadence startup overlay shown");
    return overlay;
}

inline void remove_overlay(lv_obj_t* overlay)
{
    if (overlay == nullptr) {
        return;
    }

    using namespace smooth_ui_toolkit;
    LvglLockGuard lock;
    lv_obj_delete(overlay);
    mclog::tagInfo(kLogTag, "Project Kadence startup overlay removed");
}

inline void set_both_neon_colours(uint32_t colour, float duration_seconds)
{
    auto& stackchan = GetStackChan();
    stackchan.leftNeonLight().setDuration(duration_seconds);
    stackchan.rightNeonLight().setDuration(duration_seconds);
    stackchan.leftNeonLight().setColor(colour);
    stackchan.rightNeonLight().setColor(colour);
}

inline void hard_blackout_rgb_arrays()
{
    // The base USB rail remains powered independently of the CoreS3 runtime.
    // Write black directly to every LED and refresh repeatedly so the external
    // LED controller latches an off state even after the main unit powers down.
    const uint32_t deadline = GetHAL().millis() + kBlackoutSettleMs;
    do {
        for (uint8_t index = 0; index < 12; ++index) {
            GetHAL().setRgbColor(index, 0, 0, 0);
        }
        GetHAL().refreshRgb();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    } while (static_cast<int32_t>(GetHAL().millis() - deadline) < 0);

    mclog::tagInfo(kLogTag, "RGB arrays hard-latched off");
}

inline void run_rgb_boot_cycle()
{
    constexpr std::array<uint32_t, 4> colours = {
        0xD71920,
        0x8A0F14,
        0xF2F2F2,
        0xD71920,
    };

    for (const uint32_t colour : colours) {
        set_both_neon_colours(colour, 0.16f);
        const uint32_t deadline = GetHAL().millis() + kColourHoldMs;
        while (static_cast<int32_t>(GetHAL().millis() - deadline) < 0) {
            GetStackChan().update();
            GetHAL().feedTheDog();
            GetHAL().delay(20);
        }
    }

    hard_blackout_rgb_arrays();
    mclog::tagInfo(kLogTag, "RGB boot cycle complete");
}

inline void run()
{
    lv_obj_t* overlay = create_project_kadence_overlay();

    // app_main starts the boot audio immediately before this startup task. The
    // combined splash hold and RGB cycle lasts about three seconds, matching the
    // boot clip so the eye is revealed as the audio finishes.
    const uint32_t splash_deadline = GetHAL().millis() + kSplashHoldMs;
    while (static_cast<int32_t>(GetHAL().millis() - splash_deadline) < 0) {
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }

    run_rgb_boot_cycle();
    hard_blackout_rgb_arrays();
    remove_overlay(overlay);
    hard_blackout_rgb_arrays();
}

}  // namespace kadence_startup
