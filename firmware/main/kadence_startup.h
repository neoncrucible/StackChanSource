#pragma once

#include <hal/hal.h>
#include <hal/board/hal_bridge.h>
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
constexpr uint32_t kRainbowHoldMs = 85;
constexpr uint32_t kBlackoutSettleMs = 500;

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

inline void hold_colour(uint32_t colour, uint32_t hold_ms, float duration_seconds)
{
    set_both_neon_colours(colour, duration_seconds);
    const uint32_t deadline = GetHAL().millis() + hold_ms;
    while (static_cast<int32_t>(GetHAL().millis() - deadline) < 0) {
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }
}

inline void hard_blackout_rgb_arrays()
{
    auto& stackchan = GetStackChan();

    // Stop the high-level neon animations first. Otherwise a later StackChan
    // update can repaint the last animated colour after the raw LEDs were cleared.
    stackchan.leftNeonLight().setDuration(0.0f);
    stackchan.rightNeonLight().setDuration(0.0f);
    stackchan.leftNeonLight().setColor(0x000000);
    stackchan.rightNeonLight().setColor(0x000000);

    const uint32_t deadline = GetHAL().millis() + kBlackoutSettleMs;
    do {
        GetStackChan().update();
        for (uint8_t index = 0; index < 12; ++index) {
            GetHAL().setRgbColor(index, 0, 0, 0);
        }
        GetHAL().refreshRgb();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    } while (static_cast<int32_t>(GetHAL().millis() - deadline) < 0);

    mclog::tagInfo(kLogTag, "RGB animations stopped and arrays hard-latched off");
}

inline void run_rgb_boot_cycle()
{
    constexpr std::array<uint32_t, 4> signature_colours = {
        0xD71920,
        0x8A0F14,
        0xF2F2F2,
        0xD71920,
    };

    for (const uint32_t colour : signature_colours) {
        hold_colour(colour, kColourHoldMs, 0.16f);
    }

    // Final fast full-spectrum flourish before both arrays are forced dark.
    constexpr std::array<uint32_t, 7> rainbow = {
        0xFF0000,
        0xFF7F00,
        0xFFFF00,
        0x00FF00,
        0x00BFFF,
        0x0000FF,
        0x8B00FF,
    };

    for (const uint32_t colour : rainbow) {
        hold_colour(colour, kRainbowHoldMs, 0.05f);
    }

    hard_blackout_rgb_arrays();
    mclog::tagInfo(kLogTag, "RGB boot cycle and full-colour sweep complete");
}

inline void run()
{
    // The board bridge creates this overlay immediately after LVGL becomes
    // available. Reuse that exact object so there is no second splash or visual
    // handoff. Fall back to creating it here only if early creation was skipped.
    lv_obj_t* overlay = hal_bridge::take_kadence_boot_overlay();
    if (overlay == nullptr) {
        overlay = create_project_kadence_overlay();
    } else {
        mclog::tagInfo(kLogTag, "early Project Kadence overlay adopted");
    }

    const uint32_t splash_deadline = GetHAL().millis() + kSplashHoldMs;
    while (static_cast<int32_t>(GetHAL().millis() - splash_deadline) < 0) {
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }

    run_rgb_boot_cycle();
    remove_overlay(overlay);
    hard_blackout_rgb_arrays();
}

}  // namespace kadence_startup
