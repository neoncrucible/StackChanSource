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
constexpr uint32_t kSplashHoldMs = 1400;
constexpr uint32_t kColourHoldMs = 220;

inline void show_project_kadence_splash()
{
    using namespace smooth_ui_toolkit;

    LvglLockGuard lock;
    lv_obj_t* screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(screen, 0, LV_PART_MAIN);

    lv_obj_t* title = lv_label_create(screen);
    lv_label_set_text(title, "PROJECT KADENCE");
    lv_obj_set_style_text_color(title, lv_color_hex(0xD71920), LV_PART_MAIN);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_24, LV_PART_MAIN);
    lv_obj_align(title, LV_ALIGN_CENTER, 0, -12);

    lv_obj_t* subtitle = lv_label_create(screen);
    lv_label_set_text(subtitle, "ALPHA 1");
    lv_obj_set_style_text_color(subtitle, lv_color_hex(0xE8E8E8), LV_PART_MAIN);
    lv_obj_set_style_text_font(subtitle, &lv_font_montserrat_14, LV_PART_MAIN);
    lv_obj_align(subtitle, LV_ALIGN_CENTER, 0, 24);

    lv_obj_t* line = lv_obj_create(screen);
    lv_obj_remove_flag(line, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(line, 190, 2);
    lv_obj_set_style_bg_color(line, lv_color_hex(0xD71920), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(line, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_border_width(line, 0, LV_PART_MAIN);
    lv_obj_align(line, LV_ALIGN_CENTER, 0, 49);

    lv_obj_invalidate(screen);
    mclog::tagInfo(kLogTag, "Project Kadence splash shown");
}

inline void set_both_neon_colours(uint32_t colour, float duration_seconds)
{
    auto& stackchan = GetStackChan();
    stackchan.leftNeonLight().setDuration(duration_seconds);
    stackchan.rightNeonLight().setDuration(duration_seconds);
    stackchan.leftNeonLight().setColor(colour);
    stackchan.rightNeonLight().setColor(colour);
}

inline void run_rgb_boot_cycle()
{
    constexpr std::array<uint32_t, 5> colours = {
        0xD71920,  // Kadence red
        0x8A0F14,  // deep red
        0xF2F2F2,  // white
        0xD71920,  // red return
        0x000000,  // off
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

    mclog::tagInfo(kLogTag, "RGB boot cycle complete; arrays off");
}

inline void run()
{
    show_project_kadence_splash();

    const uint32_t splash_deadline = GetHAL().millis() + kSplashHoldMs;
    while (static_cast<int32_t>(GetHAL().millis() - splash_deadline) < 0) {
        GetStackChan().update();
        GetHAL().feedTheDog();
        GetHAL().delay(20);
    }

    run_rgb_boot_cycle();
}

}  // namespace kadence_startup
