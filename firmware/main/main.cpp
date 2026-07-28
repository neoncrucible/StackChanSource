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
#include <board.h>
#include <audio_codec.h>
#include <esp_random.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

#include "kade_assets_generated.h"

using namespace smooth_ui_toolkit;

namespace {

constexpr const char* kLogTag = "KADE-EYE";

lv_obj_t* g_eye_image = nullptr;
lv_image_dsc_t g_idle1_dsc{};
lv_image_dsc_t g_idle2_dsc{};
lv_image_dsc_t g_blink_dsc{};
lv_image_dsc_t g_blink2_dsc{};
lv_image_dsc_t g_listening_dsc{};
lv_image_dsc_t g_error_dsc{};

enum class EyeState {
    IdlePrimary,
    IdleSecondary,
    BlinkClosing,
    BlinkClosed,
    BlinkOpening,
};

struct EyeRuntime {
    EyeState state = EyeState::IdlePrimary;
    uint32_t state_deadline_ms = 0;
    uint32_t next_blink_ms = 0;
    uint32_t next_idle_variation_ms = 0;
};

EyeRuntime g_eye_runtime;

uint32_t random_between(uint32_t minimum, uint32_t maximum)
{
    return minimum + (esp_random() % (maximum - minimum + 1));
}

bool deadline_reached(uint32_t now, uint32_t deadline)
{
    return static_cast<int32_t>(now - deadline) >= 0;
}

lv_image_dsc_t make_png_descriptor(const uint8_t* data, std::size_t size)
{
    lv_image_dsc_t descriptor{};
    descriptor.header.magic = LV_IMAGE_HEADER_MAGIC;
    descriptor.header.cf = LV_COLOR_FORMAT_RAW;
    descriptor.data_size = static_cast<uint32_t>(size);
    descriptor.data = data;
    return descriptor;
}

void initialise_image_descriptors()
{
    g_idle1_dsc = make_png_descriptor(kade_assets::idle1_png, kade_assets::idle1_png_size);
    g_idle2_dsc = make_png_descriptor(kade_assets::idle2_png, kade_assets::idle2_png_size);
    g_blink_dsc = make_png_descriptor(kade_assets::blink_png, kade_assets::blink_png_size);
    g_blink2_dsc = make_png_descriptor(kade_assets::blink2_png, kade_assets::blink2_png_size);
    g_listening_dsc = make_png_descriptor(kade_assets::listening_png, kade_assets::listening_png_size);
    g_error_dsc = make_png_descriptor(kade_assets::error_png, kade_assets::error_png_size);
}

void show_frame(const lv_image_dsc_t& frame)
{
    LvglLockGuard lock;
    lv_image_set_src(g_eye_image, &frame);
    lv_obj_invalidate(g_eye_image);
}

void initialise_eye_surface()
{
    initialise_image_descriptors();

    LvglLockGuard lock;
    lv_obj_t* screen = lv_screen_active();
    lv_obj_clean(screen);
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x000000), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
    lv_obj_set_style_border_width(screen, 0, LV_PART_MAIN);

    g_eye_image = lv_image_create(screen);
    lv_image_set_src(g_eye_image, &g_idle1_dsc);
    lv_obj_set_size(g_eye_image, 320, 240);
    lv_obj_center(g_eye_image);

    const uint32_t now = GetHAL().millis();
    g_eye_runtime.state = EyeState::IdlePrimary;
    g_eye_runtime.next_blink_ms = now + random_between(3000, 8000);
    g_eye_runtime.next_idle_variation_ms = now + random_between(9000, 16000);
}

void update_eye_state(uint32_t now)
{
    switch (g_eye_runtime.state) {
        case EyeState::BlinkClosing:
            if (deadline_reached(now, g_eye_runtime.state_deadline_ms)) {
                show_frame(g_blink_dsc);
                g_eye_runtime.state = EyeState::BlinkClosed;
                g_eye_runtime.state_deadline_ms = now + 120;
            }
            return;

        case EyeState::BlinkClosed:
            if (deadline_reached(now, g_eye_runtime.state_deadline_ms)) {
                show_frame(g_blink2_dsc);
                g_eye_runtime.state = EyeState::BlinkOpening;
                g_eye_runtime.state_deadline_ms = now + 60;
            }
            return;

        case EyeState::BlinkOpening:
            if (deadline_reached(now, g_eye_runtime.state_deadline_ms)) {
                show_frame(g_idle1_dsc);
                g_eye_runtime.state = EyeState::IdlePrimary;
                g_eye_runtime.next_blink_ms = now + random_between(3000, 8000);
                if (deadline_reached(now, g_eye_runtime.next_idle_variation_ms)) {
                    g_eye_runtime.next_idle_variation_ms = now + random_between(9000, 16000);
                }
            }
            return;

        case EyeState::IdleSecondary:
            if (deadline_reached(now, g_eye_runtime.state_deadline_ms)) {
                show_frame(g_idle1_dsc);
                g_eye_runtime.state = EyeState::IdlePrimary;
                g_eye_runtime.next_idle_variation_ms = now + random_between(9000, 16000);
            }
            break;

        case EyeState::IdlePrimary:
            break;
    }

    if (deadline_reached(now, g_eye_runtime.next_blink_ms)) {
        if (g_eye_runtime.state == EyeState::IdleSecondary) {
            show_frame(g_idle1_dsc);
        }
        show_frame(g_blink2_dsc);
        g_eye_runtime.state = EyeState::BlinkClosing;
        g_eye_runtime.state_deadline_ms = now + 60;
        return;
    }

    const int32_t time_until_blink = static_cast<int32_t>(g_eye_runtime.next_blink_ms - now);
    if (g_eye_runtime.state == EyeState::IdlePrimary &&
        deadline_reached(now, g_eye_runtime.next_idle_variation_ms) &&
        time_until_blink > 2200) {
        show_frame(g_idle2_dsc);
        g_eye_runtime.state = EyeState::IdleSecondary;
        g_eye_runtime.state_deadline_ms = now + random_between(700, 1500);
    }
}

uint16_t read_u16_le(const uint8_t* data)
{
    return static_cast<uint16_t>(data[0]) |
           (static_cast<uint16_t>(data[1]) << 8);
}

uint32_t read_u32_le(const uint8_t* data)
{
    return static_cast<uint32_t>(data[0]) |
           (static_cast<uint32_t>(data[1]) << 8) |
           (static_cast<uint32_t>(data[2]) << 16) |
           (static_cast<uint32_t>(data[3]) << 24);
}

int32_t read_pcm_sample(const uint8_t* data, uint16_t bits_per_sample)
{
    switch (bits_per_sample) {
        case 8:
            return (static_cast<int32_t>(data[0]) - 128) << 8;
        case 16:
            return static_cast<int16_t>(read_u16_le(data));
        case 24: {
            int32_t value = static_cast<int32_t>(data[0]) |
                            (static_cast<int32_t>(data[1]) << 8) |
                            (static_cast<int32_t>(data[2]) << 16);
            if (value & 0x00800000) {
                value |= 0xFF000000;
            }
            return value >> 8;
        }
        case 32:
            return static_cast<int32_t>(read_u32_le(data)) >> 16;
        default:
            return 0;
    }
}

bool decode_wav_to_mono(const uint8_t* wav, std::size_t wav_size, uint32_t output_rate,
                        std::vector<int16_t>& output)
{
    if (wav_size < 44 || std::memcmp(wav, "RIFF", 4) != 0 ||
        std::memcmp(wav + 8, "WAVE", 4) != 0) {
        mclog::tagError(kLogTag, "boot audio is not a RIFF/WAVE file");
        return false;
    }

    uint16_t audio_format = 0;
    uint16_t channels = 0;
    uint16_t bits_per_sample = 0;
    uint32_t source_rate = 0;
    const uint8_t* pcm_data = nullptr;
    std::size_t pcm_size = 0;

    std::size_t offset = 12;
    while (offset + 8 <= wav_size) {
        const uint8_t* chunk = wav + offset;
        const uint32_t chunk_size = read_u32_le(chunk + 4);
        const std::size_t chunk_data_offset = offset + 8;
        if (chunk_data_offset + chunk_size > wav_size) {
            mclog::tagError(kLogTag, "boot WAV contains a truncated chunk");
            return false;
        }

        if (std::memcmp(chunk, "fmt ", 4) == 0 && chunk_size >= 16) {
            const uint8_t* format = wav + chunk_data_offset;
            audio_format = read_u16_le(format);
            channels = read_u16_le(format + 2);
            source_rate = read_u32_le(format + 4);
            bits_per_sample = read_u16_le(format + 14);
        } else if (std::memcmp(chunk, "data", 4) == 0) {
            pcm_data = wav + chunk_data_offset;
            pcm_size = chunk_size;
        }

        offset = chunk_data_offset + chunk_size + (chunk_size & 1U);
    }

    if (audio_format != 1 || (channels != 1 && channels != 2) ||
        (bits_per_sample != 8 && bits_per_sample != 16 &&
         bits_per_sample != 24 && bits_per_sample != 32) ||
        source_rate == 0 || output_rate == 0 || pcm_data == nullptr) {
        mclog::tagError(kLogTag,
                        "unsupported boot WAV: format={}, channels={}, bits={}, rate={}",
                        audio_format, channels, bits_per_sample, source_rate);
        return false;
    }

    const std::size_t bytes_per_sample = bits_per_sample / 8;
    const std::size_t bytes_per_frame = bytes_per_sample * channels;
    const std::size_t source_frames = pcm_size / bytes_per_frame;
    if (source_frames == 0) {
        mclog::tagError(kLogTag, "boot WAV contains no PCM frames");
        return false;
    }

    const std::size_t output_frames = static_cast<std::size_t>(
        (static_cast<uint64_t>(source_frames) * output_rate) / source_rate);
    output.resize(std::max<std::size_t>(output_frames, 1));

    for (std::size_t output_index = 0; output_index < output.size(); ++output_index) {
        const std::size_t source_index = std::min<std::size_t>(
            (static_cast<uint64_t>(output_index) * source_rate) / output_rate,
            source_frames - 1);
        const uint8_t* frame = pcm_data + source_index * bytes_per_frame;
        int32_t sample = read_pcm_sample(frame, bits_per_sample);
        if (channels == 2) {
            sample += read_pcm_sample(frame + bytes_per_sample, bits_per_sample);
            sample /= 2;
        }
        output[output_index] = static_cast<int16_t>(
            std::clamp<int32_t>(sample, INT32_C(-32768), INT32_C(32767)));
    }

    mclog::tagInfo(kLogTag, "boot WAV decoded: {} Hz -> {} Hz, {} samples",
                   source_rate, output_rate, output.size());
    return true;
}

void boot_audio_task(void*)
{
    AudioCodec* codec = Board::GetInstance().GetAudioCodec();
    if (codec == nullptr) {
        mclog::tagError(kLogTag, "audio codec unavailable");
        vTaskDelete(nullptr);
        return;
    }

    codec->Start();
    codec->EnableOutput(true);

    std::vector<int16_t> pcm;
    if (decode_wav_to_mono(kade_assets::boot_wav, kade_assets::boot_wav_size,
                           codec->output_sample_rate(), pcm)) {
        codec->OutputData(pcm);
        mclog::tagInfo(kLogTag, "boot sound playback complete");
    }

    vTaskDelay(pdMS_TO_TICKS(100));
    codec->EnableOutput(false);
    vTaskDelete(nullptr);
}

void start_boot_audio()
{
    const BaseType_t result = xTaskCreate(
        boot_audio_task,
        "kade_boot_audio",
        6144,
        nullptr,
        4,
        nullptr);
    if (result != pdPASS) {
        mclog::tagError(kLogTag, "failed to create boot audio task");
    }
}

}  // namespace

extern "C" void app_main(void)
{
    mclog::set_level(mclog::level_info);
    mclog::set_time_format(mclog::time_format_unix_milliseconds);
    mclog::tagInfo(kLogTag, "starting Kade Eye v0.1");

    // Retain the official factory HAL initialisation path.
    GetHAL().init();

    // This checkpoint is deliberately stationary. Never issue position
    // commands, disable automatic motion behaviour and release both torques.
    auto& motion = GetStackChan().motion();
    motion.setAutoAngleSyncEnabled(false);
    motion.setAutoTorqueReleaseEnabled(false);
    motion.setTorqueEnabled(false);

    initialise_eye_surface();
    start_boot_audio();

    mclog::tagInfo(kLogTag, "Kade Eye v0.1 stationary runtime ready");

    while (true) {
        const uint32_t now = GetHAL().millis();
        update_eye_state(now);
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();
        GetHAL().delay(20);
    }
}
