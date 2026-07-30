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
#include <application.h>
#include <assets.h>
#include <audio_service.h>
#include <esp_random.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "kade_assets_generated.h"
#include "kadence_idle_motion.h"
#include "kadence_startup.h"
#include "kadence_voice_transport.h"
#include "safe_motion_foundation.h"

using namespace smooth_ui_toolkit;

namespace {

constexpr const char* kLogTag = "KADE-EYE";
constexpr uint32_t kIdleMotionConfirmationMs = 1000;
constexpr uint32_t kListeningPulseMs = 550;
constexpr uint32_t kListeningCueGuardMs = 100;
constexpr uint32_t kCaptureDurationMs = 10000;
constexpr uint32_t kTransportConnectTimeoutMs = 22000;
constexpr uint32_t kTranscriptTimeoutMs = 30000;
constexpr uint32_t kErrorDisplayMs = 1800;

constexpr uint32_t kTouchEventPress = 1U << 0;
constexpr uint32_t kTouchEventRelease = 1U << 1;
constexpr uint32_t kTouchEventSwipeForward = 1U << 2;
constexpr uint32_t kTouchEventSwipeBackward = 1U << 3;
constexpr uint32_t kTouchEventAnySwipe =
    kTouchEventSwipeForward | kTouchEventSwipeBackward;

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
    Connecting,
    Listening,
    Transcribing,
    Error,
};

struct VoiceUiRuntime {
    VoiceUiState state = VoiceUiState::Idle;
    uint32_t next_pulse_ms = 0;
    uint32_t state_deadline_ms = 0;
    bool green_frame_visible = true;
};

EyeRuntime g_eye_runtime;
VoiceUiRuntime g_voice_ui_runtime;
kadence_idle_motion::Service g_idle_motion;
kadence_voice_transport::Service g_voice_transport;
std::atomic<uint32_t> g_head_touch_events{0};
std::atomic<bool> g_startup_complete{false};
std::atomic<bool> g_listening_cue_active{false};
std::atomic<bool> g_listening_cue_complete{false};
std::atomic<bool> g_voice_capture_allowed{false};
std::atomic<bool> g_kadence_wake_detected{false};
std::atomic<bool> g_boot_audio_active{false};
AudioService* g_audio_service = nullptr;
bool g_wake_word_service_ready = false;
bool g_wake_word_detection_enabled = false;
bool g_network_start_requested = false;

bool g_touch_active = false;
bool g_touch_swiped = false;
int g_head_touch_connection = -1;

bool start_listening_cue_audio();
bool initialise_kadence_wake_word();
void set_wake_word_detection(bool enable);
void begin_listening_sequence(uint32_t now);
void cancel_listening_sequence(uint32_t now, const char* reason);

uint32_t random_between(uint32_t minimum, uint32_t maximum)
{
    return minimum + (esp_random() % (maximum - minimum + 1));
}

bool deadline_reached(uint32_t now, uint32_t deadline)
{
    return static_cast<int32_t>(now - deadline) >= 0;
}

const char* reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
        case ESP_RST_POWERON:
            return "power-on";
        case ESP_RST_EXT:
            return "external-reset";
        case ESP_RST_SW:
            return "software-reset";
        case ESP_RST_PANIC:
            return "panic";
        case ESP_RST_INT_WDT:
            return "interrupt-watchdog";
        case ESP_RST_TASK_WDT:
            return "task-watchdog";
        case ESP_RST_WDT:
            return "other-watchdog";
        case ESP_RST_DEEPSLEEP:
            return "deep-sleep";
        case ESP_RST_BROWNOUT:
            return "brownout";
        case ESP_RST_SDIO:
            return "sdio";
        case ESP_RST_UNKNOWN:
        default:
            return "unknown-or-other";
    }
}

void log_reset_reason()
{
    const esp_reset_reason_t reason = esp_reset_reason();
    mclog::tagInfo(kLogTag,
                   "ESP reset reason: {} ({})",
                   reset_reason_name(reason),
                   static_cast<int>(reason));
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

void restore_idle_voice_state(uint32_t now)
{
    g_voice_capture_allowed.store(false);
    g_listening_cue_complete.store(false);
    g_voice_ui_runtime.state = VoiceUiState::Idle;
    g_voice_ui_runtime.next_pulse_ms = 0;
    g_voice_ui_runtime.state_deadline_ms = 0;
    reset_eye_runtime(now);

    if (!g_listening_cue_active.load() && !g_voice_transport.busy()) {
        set_wake_word_detection(true);
    }
}

void fail_voice_sequence(uint32_t now, const std::string& message)
{
    mclog::tagError(kLogTag, "voice checkpoint error: {}", message);
    g_voice_capture_allowed.store(false);
    g_voice_transport.cancel();
    show_frame(g_error_dsc);
    g_voice_ui_runtime.state = VoiceUiState::Error;
    g_voice_ui_runtime.state_deadline_ms = now + kErrorDisplayMs;
}

void update_listening_pulse(uint32_t now)
{
    if (!deadline_reached(now, g_voice_ui_runtime.next_pulse_ms)) {
        return;
    }

    g_voice_ui_runtime.green_frame_visible =
        !g_voice_ui_runtime.green_frame_visible;
    show_frame(g_voice_ui_runtime.green_frame_visible
                   ? g_listening2_dsc
                   : g_error_dsc);
    g_voice_ui_runtime.next_pulse_ms = now + kListeningPulseMs;
}

void update_voice_ui(uint32_t now)
{
    g_voice_transport.update();

    std::string transport_error;
    if (g_voice_ui_runtime.state != VoiceUiState::Idle &&
        g_voice_ui_runtime.state != VoiceUiState::Error &&
        g_voice_transport.take_error(transport_error)) {
        fail_voice_sequence(now, transport_error);
        return;
    }

    switch (g_voice_ui_runtime.state) {
        case VoiceUiState::CuePlaying:
            if (g_listening_cue_complete.exchange(false)) {
                g_voice_ui_runtime.state = VoiceUiState::Connecting;
                g_voice_ui_runtime.green_frame_visible = true;
                g_voice_ui_runtime.next_pulse_ms = now + kListeningPulseMs;
                g_voice_ui_runtime.state_deadline_ms =
                    now + kTransportConnectTimeoutMs;
                show_frame(g_listening2_dsc);

                if (!g_voice_transport.begin_capture()) {
                    fail_voice_sequence(now, "voice transport was already busy");
                    return;
                }

                mclog::tagInfo(kLogTag,
                               "listening cue complete; discovering Windows transcript server");
            }
            return;

        case VoiceUiState::Connecting:
            if (g_voice_transport.take_capture_started()) {
                g_voice_capture_allowed.store(true);
                g_voice_ui_runtime.state = VoiceUiState::Listening;
                g_voice_ui_runtime.state_deadline_ms = now + kCaptureDurationMs;
                mclog::tagInfo(kLogTag,
                               "robot microphone capture gate open; 10-second transcript sample started");
                return;
            }
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                fail_voice_sequence(now, "Windows transcript connection timed out");
                return;
            }
            update_listening_pulse(now);
            return;

        case VoiceUiState::Listening:
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                g_voice_capture_allowed.store(false);
                g_voice_transport.request_transcript();
                g_voice_ui_runtime.state = VoiceUiState::Transcribing;
                g_voice_ui_runtime.state_deadline_ms = now + kTranscriptTimeoutMs;
                show_frame(g_listening2_dsc);
                mclog::tagInfo(kLogTag,
                               "voice sample complete; waiting for Faster Whisper transcript on Windows");
                return;
            }
            update_listening_pulse(now);
            return;

        case VoiceUiState::Transcribing: {
            std::string transcript;
            if (g_voice_transport.take_transcript(transcript)) {
                mclog::tagInfo(kLogTag,
                               "WINDOWS TRANSCRIPT: {}",
                               transcript.empty() ? "<no speech recognised>" : transcript);
                g_voice_transport.complete_session();
                restore_idle_voice_state(now);
                return;
            }
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                fail_voice_sequence(now, "Windows transcript response timed out");
                return;
            }
            return;
        }

        case VoiceUiState::Error:
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                restore_idle_voice_state(now);
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

    const int32_t time_until_blink =
        static_cast<int32_t>(g_eye_runtime.next_blink_ms - now);
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
                   "head-touch control connected (signal connection {})",
                   g_head_touch_connection);
}

void cancel_listening_sequence(uint32_t now, const char* reason)
{
    if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
        return;
    }

    g_voice_capture_allowed.store(false);
    g_listening_cue_complete.store(false);
    g_voice_transport.cancel();
    restore_idle_voice_state(now);
    mclog::tagInfo(kLogTag, "listening cancelled: {}", reason);
}

void process_head_touch_events(uint32_t now)
{
    const uint32_t events = g_head_touch_events.exchange(0);

    if ((events & kTouchEventPress) != 0U) {
        g_touch_active = true;
        g_touch_swiped = false;
    }

    const bool swipe_detected = (events & kTouchEventAnySwipe) != 0U;
    if (swipe_detected) {
        g_touch_swiped = true;
        if (g_voice_ui_runtime.state != VoiceUiState::Idle) {
            cancel_listening_sequence(now, "head swipe");
            g_touch_active = false;
            g_touch_swiped = false;
            return;
        }
    }

    if ((events & kTouchEventRelease) == 0U) {
        return;
    }

    if (g_touch_active && !g_touch_swiped &&
        g_voice_ui_runtime.state == VoiceUiState::Idle) {
        g_idle_motion.toggle();
        show_idle_motion_confirmation(now);
        mclog::tagInfo(kLogTag,
                       "touch toggle: idle motion {}",
                       g_idle_motion.enabled() ? "enabled" : "disabled");
    }

    g_touch_active = false;
    g_touch_swiped = false;
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

bool decode_wav_to_mono(const uint8_t* wav,
                        std::size_t wav_size,
                        uint32_t output_rate,
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
                        audio_format,
                        channels,
                        bits_per_sample,
                        source_rate);
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

    mclog::tagInfo(kLogTag,
                   "embedded WAV decoded: {} Hz -> {} Hz, {} samples",
                   source_rate,
                   output_rate,
                   output.size());
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

    vTaskDelay(pdMS_TO_TICKS(kListeningCueGuardMs));
    codec->EnableOutput(false);
    return decoded;
}

void boot_audio_task(void*)
{
    (void)play_embedded_wav(
        kade_assets::boot_wav, kade_assets::boot_wav_size, "boot sound");
    g_boot_audio_active.store(false);
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
        g_listening_cue_active.load() || g_voice_transport.busy()) {
        return;
    }

    set_wake_word_detection(false);
    g_idle_motion.set_enabled(false);
    g_eye_runtime.confirmation_active = false;
    g_voice_capture_allowed.store(false);
    g_voice_ui_runtime.state = VoiceUiState::CuePlaying;
    g_voice_ui_runtime.green_frame_visible = true;
    show_frame(g_listening2_dsc);

    if (!start_listening_cue_audio()) {
        fail_voice_sequence(now, "listening chirp could not start");
        return;
    }

    mclog::tagInfo(kLogTag,
                   "Kadence wake accepted; green listening frame and chirp started");
}

void set_wake_word_detection(bool enable)
{
    if (g_audio_service == nullptr || !g_wake_word_service_ready) {
        return;
    }
    if (enable == g_wake_word_detection_enabled) {
        return;
    }

    g_audio_service->EnableWakeWordDetection(enable);
    g_wake_word_detection_enabled =
        enable && g_audio_service->IsWakeWordRunning();
    mclog::tagInfo(kLogTag,
                   "Kadence wake-word detection {}",
                   g_wake_word_detection_enabled ? "armed" : "disarmed");
}

bool initialise_kadence_wake_word()
{
    AudioCodec* codec = Board::GetInstance().GetAudioCodec();
    if (codec == nullptr) {
        mclog::tagError(kLogTag,
                        "cannot initialise Kadence wake word: audio codec unavailable");
        return false;
    }

    auto& audio_service = Application::GetInstance().GetAudioService();
    g_audio_service = &audio_service;
    g_voice_transport.initialise(g_audio_service);

    AudioServiceCallbacks callbacks{};
    callbacks.on_send_queue_available = []() {
        g_voice_transport.notify_send_queue_available();
    };
    callbacks.on_wake_word_detected = [](const std::string& wake_word) {
        mclog::tagInfo(kLogTag, "wake-word callback: {}", wake_word);
        if (wake_word == "Kadence") {
            g_kadence_wake_detected.store(true);
        }
    };
    audio_service.SetCallbacks(callbacks);
    audio_service.Initialize(codec);
    audio_service.Start();

    if (!Assets::GetInstance().Apply()) {
        mclog::tagError(kLogTag,
                        "failed to apply speech-model assets for Kadence wake word");
        return false;
    }

    g_wake_word_service_ready = true;
    mclog::tagInfo(kLogTag,
                   "Kadence wake-word service initialised; arming after startup audio");
    return true;
}

void start_boot_audio()
{
    g_boot_audio_active.store(true);
    const BaseType_t result = xTaskCreate(
        boot_audio_task,
        "kade_boot_audio",
        6144,
        nullptr,
        4,
        nullptr);
    if (result != pdPASS) {
        g_boot_audio_active.store(false);
        mclog::tagError(kLogTag, "failed to create boot audio task");
    }
}

void project_kadence_startup_task(void*)
{
    kadence_startup::run();

    const bool rest_reached = kadence_motion::go_to_rest_pose();
    if (rest_reached) {
        mclog::tagInfo(kLogTag,
                       "startup rest pose [80,300] reached and servo torque released");
    } else {
        mclog::tagError(kLogTag,
                        "startup rest pose failed; motion stopped and servo torque released");
    }

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
    mclog::tagInfo(kLogTag,
                   "starting Project Kadence transcript-transport checkpoint");
    log_reset_reason();

    GetHAL().init();

    kadence_motion::restore_factory_idle_policy(GetStackChan().motion());
    g_idle_motion.initialise();
    (void)initialise_kadence_wake_word();

    initialise_eye_surface();
    initialise_head_touch_toggle();
    start_boot_audio();
    start_project_kadence_startup();

    mclog::tagInfo(kLogTag,
                   "runtime ready; tap toggles idle motion; either swipe cancels voice");

    while (true) {
        const uint32_t now = GetHAL().millis();

        if (g_startup_complete.load()) {
            GetStackChan().update();
            process_head_touch_events(now);

            if (!g_boot_audio_active.load() && !g_network_start_requested) {
                g_network_start_requested = true;
                g_voice_transport.start_network();
            }

            if (g_kadence_wake_detected.exchange(false)) {
                begin_listening_sequence(now);
            }

            if (!g_boot_audio_active.load() &&
                !g_listening_cue_active.load() &&
                g_voice_ui_runtime.state == VoiceUiState::Idle &&
                !g_voice_transport.busy() &&
                g_wake_word_service_ready &&
                !g_wake_word_detection_enabled) {
                set_wake_word_detection(true);
            }

            if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
                g_idle_motion.update();
            }
        } else {
            g_head_touch_events.exchange(0);
            g_touch_active = false;
            g_touch_swiped = false;
        }

        update_voice_ui(now);
        update_eye_state(now);
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();
        GetHAL().delay(20);
    }
}
