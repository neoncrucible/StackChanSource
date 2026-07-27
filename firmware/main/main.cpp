/*
 * Kade Eye v0.1
 *
 * Minimal stationary identity smoke test for the M5Stack StackChan:
 * - official factory HAL
 * - custom full-screen optic avatar
 * - irregular blink animation
 * - one boot sound
 * - servo torque released and servo power disabled
 */

#include <assets/assets.h>
#include <audio_service.h>
#include <board.h>
#include <esp_random.h>
#include <hal/hal.h>
#include <lvgl.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

#include <cstddef>
#include <cstdint>
#include <string_view>

extern const char kade_boot_ogg_start[] asm("_binary_kade_boot_ogg_start");
extern const char kade_boot_ogg_end[] asm("_binary_kade_boot_ogg_end");

namespace {

constexpr std::string_view KADE_BOOT_OGG{
    kade_boot_ogg_start,
    static_cast<std::size_t>(kade_boot_ogg_end - kade_boot_ogg_start),
};

constexpr uint32_t BLINK_HALF_MS = 60;
constexpr uint32_t BLINK_CLOSED_MS = 120;
constexpr uint32_t BLINK_INTERVAL_MIN_MS = 3000;
constexpr uint32_t BLINK_INTERVAL_MAX_MS = 8000;
constexpr uint32_t IDLE_SHIFT_MIN_MS = 12000;
constexpr uint32_t IDLE_SHIFT_MAX_MS = 25000;

struct EyeAssets {
    lv_image_dsc_t idle1;
    lv_image_dsc_t idle2;
    lv_image_dsc_t blink;
    lv_image_dsc_t blink2;
    lv_image_dsc_t listening;
    lv_image_dsc_t error;
};

uint32_t random_between(uint32_t minimum, uint32_t maximum)
{
    return minimum + (esp_random() % (maximum - minimum + 1));
}

bool deadline_reached(uint32_t now, uint32_t deadline)
{
    return static_cast<int32_t>(now - deadline) >= 0;
}

bool is_valid_image(const lv_image_dsc_t& image)
{
    return image.data != nullptr && image.data_size > 0;
}

void set_eye_frame(lv_obj_t* image_object, const lv_image_dsc_t& frame)
{
    LvglLockGuard lock;
    lv_image_set_src(image_object, &frame);
}

lv_obj_t* create_eye_view(const EyeAssets& assets)
{
    LvglLockGuard lock;

    lv_obj_t* screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(screen, lv_color_black(), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);

    if (!is_valid_image(assets.idle1) || !is_valid_image(assets.idle2) ||
        !is_valid_image(assets.blink) || !is_valid_image(assets.blink2) ||
        !is_valid_image(assets.listening) || !is_valid_image(assets.error)) {
        lv_obj_t* label = lv_label_create(screen);
        lv_label_set_text(label, "KADE EYE\nASSET ERROR");
        lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
        lv_obj_set_style_text_color(label, lv_color_hex(0xFF4040), LV_PART_MAIN);
        lv_obj_center(label);
        return nullptr;
    }

    lv_obj_t* image_object = lv_image_create(screen);
    lv_image_set_src(image_object, &assets.idle1);
    lv_obj_set_size(image_object, 320, 240);
    lv_obj_center(image_object);
    return image_object;
}

void run_blink(lv_obj_t* image_object, const EyeAssets& assets, const lv_image_dsc_t& idle_frame)
{
    set_eye_frame(image_object, assets.blink2);
    GetHAL().delay(BLINK_HALF_MS);

    set_eye_frame(image_object, assets.blink);
    GetHAL().delay(BLINK_CLOSED_MS);

    set_eye_frame(image_object, assets.blink2);
    GetHAL().delay(BLINK_HALF_MS);

    set_eye_frame(image_object, idle_frame);
}

}  // namespace

extern "C" void app_main(void)
{
    mclog::set_level(mclog::level_info);
    mclog::set_time_format(mclog::time_format_unix_milliseconds);
    mclog::tagInfo("KadeEye", "starting v0.1");

    GetHAL().init();

    // Release the smart servos before removing their dedicated power rail.
    // This firmware never sends a movement or home-position command.
    auto& motion = GetStackChan().motion();
    motion.setAutoAngleSyncEnabled(false);
    motion.setAutoTorqueReleaseEnabled(false);
    motion.setTorqueEnabled(false);
    GetHAL().setServoPowerEnabled(false);
    mclog::tagInfo("KadeEye", "servo torque released and servo power disabled");

    const EyeAssets assets{
        .idle1 = assets::get_image("kade_idle1.png"),
        .idle2 = assets::get_image("kade_idle2.png"),
        .blink = assets::get_image("kade_blink.png"),
        .blink2 = assets::get_image("kade_blink2.png"),
        .listening = assets::get_image("kade_listening.png"),
        .error = assets::get_image("kade_error.png"),
    };

    lv_obj_t* eye = create_eye_view(assets);
    if (eye == nullptr) {
        mclog::tagError("KadeEye", "one or more avatar assets could not be loaded");
        while (true) {
            GetHAL().feedTheDog();
            GetHAL().updateHeapStatusLog();
            GetHAL().delay(100);
        }
    }

    static AudioService audio_service;
    audio_service.Initialize(Board::GetInstance().GetAudioCodec());
    audio_service.Start();
    audio_service.PlaySound(KADE_BOOT_OGG);
    mclog::tagInfo("KadeEye", "boot sound queued");

    bool alternate_idle = false;
    uint32_t next_blink = GetHAL().millis() +
                          random_between(BLINK_INTERVAL_MIN_MS, BLINK_INTERVAL_MAX_MS);
    uint32_t next_idle_shift = GetHAL().millis() +
                               random_between(IDLE_SHIFT_MIN_MS, IDLE_SHIFT_MAX_MS);

    while (true) {
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();

        const uint32_t now = GetHAL().millis();

        if (deadline_reached(now, next_blink)) {
            const lv_image_dsc_t& idle_frame = alternate_idle ? assets.idle2 : assets.idle1;
            run_blink(eye, assets, idle_frame);
            next_blink = GetHAL().millis() +
                         random_between(BLINK_INTERVAL_MIN_MS, BLINK_INTERVAL_MAX_MS);
        }

        if (deadline_reached(now, next_idle_shift)) {
            alternate_idle = !alternate_idle;
            set_eye_frame(eye, alternate_idle ? assets.idle2 : assets.idle1);
            next_idle_shift = GetHAL().millis() +
                              random_between(IDLE_SHIFT_MIN_MS, IDLE_SHIFT_MAX_MS);
        }

        GetHAL().delay(20);
    }
}
