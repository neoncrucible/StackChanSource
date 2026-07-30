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
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

#include "kade_assets_generated.h"
#include "kadence_idle_motion.h"
#include "kadence_startup.h"
#include "safe_motion_foundation.h"

using namespace smooth_ui_toolkit;

namespace {

constexpr const char* kLogTag = "KADE-EYE";
constexpr uint32_t kIdleMotionConfirmationMs = 1000;
constexpr uint32_t kListeningPulseMs = 550;
constexpr uint32_t kListeningCueGuardMs = 100;
constexpr bool kEnableVoiceUiDiagnosticSwipes = true;

constexpr uint32_t kTouchEventPress = 1U << 0;
constexpr uint32_t kTouchEventRelease = 1U << 1;
constexpr uint32_t kTouchEventSwipeForward = 1U << 2;
constexpr uint32_t kTouchEventSwipeBackward = 1U << 3;

lv_obj_t* g_eye_image = nullptr;
lv_image_dsc_t g_idle1_dsc{};
lv_image_dsc_t g_idle2_dsc{};
lv_image_dsc_t g_blink_dsc{};
lv_image_dsc_t g_blink2_dsc{};
lv_image_dsc_t g_listening_dsc{};
lv_image_dsc_t g_listening2_dsc{};
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
    bool confirmation_active = false;
    uint32_t confirmation_deadline_ms = 0;
};

enum class VoiceUiState : uint8_t {
    Idle,
    CuePlaying,
    Listening,
};

struct VoiceUiRuntime {
    VoiceUiState state = VoiceUiState::Idle;
    uint32_t next_pulse_ms = 0;
    bool green_frame_visible = true;
};

EyeRuntime g_eye_runtime;
VoiceUiRuntime g_voice_ui_runtime;
kadence_idle_motion::Service g_idle_motion;
std::atomic<uint32_t> g_head_touch_events{0};
std::atomic<bool> g_startup_complete{false};
std::atomic<bool> g_listening_cue_active{false};
std::atomic<bool> g_listening_cue_complete{false};
std::atomic<bool> g_voice_capture_allowed{false};

bool g_touch_active = false;
bool g_touch_swiped = false;
int g_touch_swipe_direction = 0;
int g_head_touch_connection = -1;

bool start_listening_cue_audio();
void begin_listening_sequence(uint32_t now);
void stop_listening_sequence(uint32_t now);

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
    g_listening2_dsc = make_png_descriptor(kade_assets::listening2_png, kade_assets::listening2_png_size);
    g_error_dsc = make_png_descriptor(kade_assets::error_png, kade_assets::error_png_size);
}

void show_frame(const lv_image_dsc_t& frame)
{
    LvglLockGuard lock;
    lv_image_set_src(g_eye_image, &frame);
    lv_obj_invalidate(g_eye_image);
}

void reset_eye_runtime(uint32_t now)
{
    show_frame(g_idle1_dsc);
    g_eye_runtime.state = EyeState::IdlePrimary;
    g_eye_runtime.state_deadline_ms = 0;
    g_eye_runtime.next_blink_ms = now + random_between(3000, 8000);
    g_eye_runtime.next_idle_variation_ms = now + random_between(9000, 16000);
}

void show_idle_motion_confirmation(uint32_t now)
{
    // Use the repository's existing listening.png asset (Image Gen 5) for both
    // toggle directions. The changed movement state is also recorded in logs.
    show_frame(g_listening_dsc);
    g_eye_runtime.confirmation_active = true;
    g_eye_runtime.confirmation_deadline_ms = now + kIdleMotionConfirmationMs;
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

void update_voice_ui(uint32_t now)
{
    switch (g_voice_ui_runtime.state) {
        case VoiceUiState::CuePlaying:
            if (g_listening_cue_complete.exchange(false)) {
                g_voice_ui_runtime.state = VoiceUiState::Listening;
                g_voice_ui_runtime.green_frame_visible = true;
                g_voice_ui_runtime.next_pulse_ms = now + kListeningPulseMs;
                g_voice_capture_allowed.store(true);
                show_frame(g_listening2_dsc);
                mclog::tagInfo(kLogTag,
                               "listening cue complete; robot microphone capture gate open");
            }
            return;

        case VoiceUiState::Listening:
            if (deadline_reached(now, g_voice_ui_runtime.next_pulse_ms)) {
                g_voice_ui_runtime.green_frame_visible =
                    !g_voice_ui_runtime.green_frame_visible;
                show_frame(g_voice_ui_runtime.green_frame_visible
                               ? g_listening2_dsc
                               : g_error_dsc);
                g_voice_ui_runtime.next_pulse_ms = now + kListeningPulseMs;
            }
            return;

        case VoiceUiState::Idle:
        default:
            return;
    }
}

void update_eye_state(uint32_t now)
{
    if (g_voice_ui_runtime.state != VoiceUiState::Idle) {
        return;
    }

    if (g_eye_runtime.confirmation_active) {
        if (deadline_reached(now, g_eye_runtime.confirmation_deadline_ms)) {
            g_eye_runtime.confirmation_active = false;
            reset_eye_runtime(now);
        }
        return;
    }

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

void initialise_head_touch_toggle()
{
    // The official Si12T task emits Press/Release/Swipe events. Keep its callback
    // minimal and consume the flags from the normal 50 Hz runtime loop.
    g_head_touch_connection = GetHAL().onHeadPetGesture.connect([](HeadPetGesture gesture) {
        switch (gesture) {
            case HeadPetGesture::Press:
                g_head_touch_events.fetch_or(kTouchEventPress);
                break;
            case HeadPetGesture::Release:
                g_head_touch_events.fetch_or(kTouchEventRelease);
                break;
            case HeadPetGesture::SwipeForward:
                g_head_touch_events.fetch_or(kTouchEventSwipeForward);
                break;
            case HeadPetGesture::SwipeBackward:
                g_head_touch_events.fetch_or(kTouchEventSwipeBackward);
                break;
            case HeadPetGesture::None:
            default:
                break;
        }
    });

    mclog::tagInfo(kLogTag,
                   "head-touch idle-motion toggle connected (signal connection {})",
                   g_head_touch_connection);
}

void process_head_touch_events(uint32_t now)
{
    const uint32_t events = g_head_touch_events.exchange(0);

    if ((events & kTouchEventPress) != 0U) {
        g_touch_active = true;
        g_touch_swiped = false;
        g_touch_swipe_direction = 0;
    }

    if ((events & kTouchEventSwipeForward) != 0U) {
        g_touch_swiped = true;
        g_touch_swipe_direction = 1;
    }
    if ((events & kTouchEventSwipeBackward) != 0U) {
        g_touch_swiped = true;
        g_touch_swipe_direction = -1;
    }

    if ((events & kTouchEventRelease) == 0U) {
        return;
    }

    // A clean tap retains the physically signed-off idle-motion toggle.
    if (g_touch_active && !g_touch_swiped &&
        g_voice_ui_runtime.state == VoiceUiState::Idle) {
        g_idle_motion.toggle();
        show_idle_motion_confirmation(now);
        mclog::tagInfo(kLogTag,
                       "touch toggle: idle motion {}",
                       g_idle_motion.enabled() ? "enabled" : "disabled");
    }

    // Temporary physical-test gate. The production wake-word callback
    // will call the same begin/stop functions without changing UI logic.
    if (g_touch_active && g_touch_swiped && kEnableVoiceUiDiagnosticSwipes) {
        if (g_touch_swipe_direction > 0) {
            begin_listening_sequence(now);
        } else if (g_touch_swipe_direction < 0) {
            stop_listening_sequence(now);
        }
    }

    g_touch_active = false;
    g_touch_swiped = false;
    g_touch_swipe_direction = 0;
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
        mclog::tagError(kLogTag, "embedded audio is not a RIFF/WAVE file");
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
            mclog::tagError(kLogTag, "embedded WAV contains a truncated chunk");
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
                        "unsupported embedded WAV: format={}, channels={}, bits={}, rate={}",
                        audio_format, channels, bits_per_sample, source_rate);
        return false;
    }

    const std::size_t bytes_per_sample = bits_per_sample / 8;
    const std::size_t bytes_per_frame = bytes_per_sample * channels;
    const std::size_t source_frames = pcm_size / bytes_per_frame;
    if (source_frames == 0) {
        mclog::tagError(kLogTag, "embedded WAV contains no PCM frames");
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

    mclog::tagInfo(kLogTag, "embedded WAV decoded: {} Hz -> {} Hz, {} samples",
                   source_rate, output_rate, output.size());
    return true;
}

bool play_embedded_wav(const uint8_t* wav, std::size_t wav_size, const char* label)
{
    AudioCodec* codec = Board::GetInstance().GetAudioCodec();
    if (codec == nullptr) {
        mclog::tagError(kLogTag, "{} audio codec unavailable", label);
        return false;
    }

    codec->Start();
    codec->EnableOutput(true);

    std::vector<int16_t> pcm;
    const bool decoded = decode_wav_to_mono(
        wav, wav_size, codec->output_sample_rate(), pcm);
    if (decoded) {
        codec->OutputData(pcm);
        mclog::tagInfo(kLogTag, "{} playback complete", label);
    }

    // Capture remains closed until the speaker path has settled.
    vTaskDelay(pdMS_TO_TICKS(kListeningCueGuardMs));
    codec->EnableOutput(false);
    return decoded;
}

void boot_audio_task(void*)
{
    (void)play_embedded_wav(
        kade_assets::boot_wav, kade_assets::boot_wav_size, "boot sound");
    vTaskDelete(nullptr);
}

void listening_cue_audio_task(void*)
{
    (void)play_embedded_wav(
        kade_assets::chirp_wav, kade_assets::chirp_wav_size, "listening chirp");
    g_listening_cue_active.store(false);
    g_listening_cue_complete.store(true);
    vTaskDelete(nullptr);
}

bool start_listening_cue_audio()
{
    if (g_listening_cue_active.exchange(true)) {
        mclog::tagError(kLogTag, "listening chirp is already active");
        return false;
    }

    g_listening_cue_complete.store(false);
    const BaseType_t result = xTaskCreate(
        listening_cue_audio_task,
        "kade_listen_cue",
        6144,
        nullptr,
        4,
        nullptr);
    if (result != pdPASS) {
        g_listening_cue_active.store(false);
        mclog::tagError(kLogTag, "failed to create listening chirp task");
        return false;
    }
    return true;
}

void begin_listening_sequence(uint32_t now)
{
    if (g_voice_ui_runtime.state != VoiceUiState::Idle ||
        g_listening_cue_active.load()) {
        return;
    }

    // Voice owns the interaction. Fail to the stationary torque-off state.
    g_idle_motion.set_enabled(false);
    g_eye_runtime.confirmation_active = false;
    g_voice_capture_allowed.store(false);
    g_voice_ui_runtime.state = VoiceUiState::CuePlaying;
    g_voice_ui_runtime.green_frame_visible = true;
    show_frame(g_listening2_dsc);

    if (!start_listening_cue_audio()) {
        g_voice_ui_runtime.state = VoiceUiState::Idle;
        show_frame(g_error_dsc);
        g_eye_runtime.confirmation_active = true;
        g_eye_runtime.confirmation_deadline_ms = now + kIdleMotionConfirmationMs;
        return;
    }

    mclog::tagInfo(kLogTag,
                   "Kadence wake accepted; green listening frame and chirp started");
}

void stop_listening_sequence(uint32_t now)
{
    if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
        return;
    }

    g_voice_capture_allowed.store(false);
    g_listening_cue_complete.store(false);
    g_voice_ui_runtime.state = VoiceUiState::Idle;
    g_voice_ui_runtime.next_pulse_ms = 0;
    reset_eye_runtime(now);
    mclog::tagInfo(kLogTag,
                   "listening stopped; microphone gate closed and idle eye restored");
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

void project_kadence_startup_task(void*)
{
    kadence_startup::run();

    // Startup completion is a stationary production state. Restore the official
    // servicing policy, explicitly release both torques, and let the main runtime
    // become the sole 50 Hz StackChan updater.
    kadence_motion::restore_factory_idle_policy(GetStackChan().motion());
    g_startup_complete.store(true);

    mclog::tagInfo(kLogTag,
                   "startup complete; idle motion is OFF and servo torque is released");
    vTaskDelete(nullptr);
}

void start_project_kadence_startup()
{
    const BaseType_t result = xTaskCreate(
        project_kadence_startup_task,
        "kade_startup",
        4096,
        nullptr,
        5,
        nullptr);
    if (result != pdPASS) {
        mclog::tagError(kLogTag, "failed to create Project Kadence startup task");
    }
}

}  // namespace

extern "C" void app_main(void)
{
    mclog::set_level(mclog::level_info);
    mclog::set_time_format(mclog::time_format_unix_milliseconds);
    mclog::tagInfo(kLogTag, "starting Project Kadence production idle-motion runtime");

    // Retain the official factory HAL initialisation path, including the Si12T
    // head-touch task and its HeadPetGesture signal.
    GetHAL().init();

    // Safe production default: no movement request means both torques are off.
    // The physically signed-off movement checkpoint remains in source as a
    // recovery diagnostic but is no longer executed automatically on boot.
    kadence_motion::restore_factory_idle_policy(GetStackChan().motion());
    g_idle_motion.initialise();

    initialise_eye_surface();
    initialise_head_touch_toggle();
    start_boot_audio();
    start_project_kadence_startup();

    mclog::tagInfo(kLogTag,
                   "runtime ready; tap toggles idle motion; forward/back swipes test voice UI");

    while (true) {
        const uint32_t now = GetHAL().millis();

        if (g_startup_complete.load()) {
            // Match the official firmware lifecycle. This is the sole permanent
            // StackChan update path after the startup task hands control over.
            GetStackChan().update();
            process_head_touch_events(now);
            if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
                g_idle_motion.update();
            }
        } else {
            // Ignore accidental startup touches and keep the boot sequence
            // stationary. The startup task services StackChan while it runs.
            g_head_touch_events.exchange(0);
            g_touch_active = false;
            g_touch_swiped = false;
            g_touch_swipe_direction = 0;
        }

        update_voice_ui(now);
        update_eye_state(now);
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();
        GetHAL().delay(20);
    }
}
