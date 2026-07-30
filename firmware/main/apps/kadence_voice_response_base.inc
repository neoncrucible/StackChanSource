#include <application.h>
#include <audio_service.h>
#include <cJSON.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <hal/hal.h>
#include <lvgl.h>
#include <mooncake_log.h>
#include <settings.h>
#include <smooth_ui_toolkit.hpp>
#include <websocket_protocol.h>

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>

#include "kade_assets_generated.h"

using namespace smooth_ui_toolkit;

namespace kadence_voice_response {
namespace {

constexpr const char* kLogTag = "KADENCE-VOICE-RX";
constexpr const char* kTranscriptPath = "/kadence/v1";
constexpr const char* kResponsePath = "/kadence/response/v1";
constexpr int64_t kReconnectDelayUs = 3000000;
constexpr uint32_t kInitialDelayMs = 12000;
constexpr uint32_t kThinkingPulseMs = 280;

enum class ResponseState : uint8_t {
    Idle,
    Thinking,
    Speaking,
    Error,
};

std::unique_ptr<WebsocketProtocol> g_protocol;
std::mutex g_protocol_mutex;
std::atomic<bool> g_connected{false};
std::atomic<bool> g_opening{false};
std::atomic<bool> g_close_requested{false};
std::atomic<int64_t> g_retry_not_before_us{0};
std::atomic<ResponseState> g_state{ResponseState::Idle};
std::atomic<uint32_t> g_audio_packets{0};

lv_image_dsc_t g_green_dsc{};
lv_image_dsc_t g_red_dsc{};
bool g_descriptors_ready = false;
bool g_thinking_green = false;
uint32_t g_next_thinking_pulse_ms = 0;

lv_image_dsc_t make_png_descriptor(const uint8_t* data, std::size_t size)
{
    lv_image_dsc_t descriptor{};
    descriptor.header.magic = LV_IMAGE_HEADER_MAGIC;
    descriptor.header.cf = LV_COLOR_FORMAT_RAW;
    descriptor.data_size = static_cast<uint32_t>(size);
    descriptor.data = data;
    return descriptor;
}

void ensure_descriptors()
{
    if (g_descriptors_ready) {
        return;
    }
    g_green_dsc = make_png_descriptor(
        kade_assets::listening2_png,
        kade_assets::listening2_png_size);
    g_red_dsc = make_png_descriptor(
        kade_assets::error_png,
        kade_assets::error_png_size);
    g_descriptors_ready = true;
}

void show_frame(const lv_image_dsc_t& frame)
{
    ensure_descriptors();
    LvglLockGuard lock;
    lv_obj_t* screen = lv_screen_active();
    if (screen == nullptr) {
        return;
    }
    lv_obj_t* image = lv_obj_get_child(screen, 0);
    if (image == nullptr) {
        return;
    }
    lv_image_set_src(image, &frame);
    lv_obj_invalidate(image);
}

void show_state(ResponseState state)
{
    switch (state) {
        case ResponseState::Thinking:
            g_thinking_green = false;
            show_frame(g_red_dsc);
            break;
        case ResponseState::Speaking:
            show_frame(g_green_dsc);
            break;
        case ResponseState::Error:
            show_frame(g_red_dsc);
            break;
        case ResponseState::Idle:
        default:
            // The main voice runtime restores the normal idle eye after the
            // transcript completion message arrives on the proven mic channel.
            break;
    }
}

void set_state(ResponseState state)
{
    g_state.store(state);
    g_next_thinking_pulse_ms = 0;
    show_state(state);
}

void handle_voice_state(const cJSON* root)
{
    const cJSON* state = cJSON_GetObjectItem(root, "state");
    if (!cJSON_IsString(state)) {
        return;
    }

    if (std::strcmp(state->valuestring, "thinking") == 0) {
        g_audio_packets.store(0);
        set_state(ResponseState::Thinking);
        mclog::tagInfo(kLogTag, "Gemini thinking state received");
    } else if (std::strcmp(state->valuestring, "speaking") == 0) {
        Application::GetInstance().GetAudioService().ResetDecoder();
        g_audio_packets.store(0);
        set_state(ResponseState::Speaking);
        const cJSON* text = cJSON_GetObjectItem(root, "text");
        mclog::tagInfo(
            kLogTag,
            "robot speaking state received{}{}",
            cJSON_IsString(text) ? ": " : "",
            cJSON_IsString(text) ? text->valuestring : "");
    } else if (std::strcmp(state->valuestring, "stop") == 0) {
        const uint32_t packets = g_audio_packets.load();
        set_state(ResponseState::Idle);
        mclog::tagInfo(
            kLogTag,
            "robot response playback complete after {} Opus packet(s)",
            packets);
    } else if (std::strcmp(state->valuestring, "error") == 0) {
        set_state(ResponseState::Error);
        const cJSON* message = cJSON_GetObjectItem(root, "message");
        mclog::tagError(
            kLogTag,
            "Windows voice response error{}{}",
            cJSON_IsString(message) ? ": " : "",
            cJSON_IsString(message) ? message->valuestring : "");
    }
}

void configure_callbacks(WebsocketProtocol& protocol)
{
    protocol.OnConnected([]() {
        mclog::tagInfo(kLogTag, "response WebSocket connected");
    });
    protocol.OnAudioChannelOpened([]() {
        g_connected.store(true);
        g_retry_not_before_us.store(0);
        mclog::tagInfo(
            kLogTag,
            "warm robot speaker channel opened; Gemini and Edge TTS responses are ready");
    });
    protocol.OnAudioChannelClosed([]() {
        g_connected.store(false);
        g_close_requested.store(true);
        g_retry_not_before_us.store(esp_timer_get_time() + kReconnectDelayUs);
        mclog::tagError(kLogTag, "robot speaker channel closed; reconnect scheduled");
    });
    protocol.OnNetworkError([](const std::string& message) {
        g_connected.store(false);
        g_close_requested.store(true);
        g_retry_not_before_us.store(esp_timer_get_time() + kReconnectDelayUs);
        mclog::tagError(
            kLogTag,
            "robot speaker WebSocket error: {}; reconnect scheduled",
            message);
    });
    protocol.OnIncomingJson([](const cJSON* root) {
        const cJSON* type = cJSON_GetObjectItem(root, "type");
        if (!cJSON_IsString(type)) {
            return;
        }
        if (std::strcmp(type->valuestring, "voice_state") == 0) {
            handle_voice_state(root);
        }
    });
    protocol.OnIncomingAudio([](std::unique_ptr<AudioStreamPacket> packet) {
        if (packet == nullptr) {
            return;
        }
        auto& audio_service = Application::GetInstance().GetAudioService();
        if (!audio_service.PushPacketToDecodeQueue(std::move(packet), true)) {
            set_state(ResponseState::Error);
            mclog::tagError(kLogTag, "failed to queue returned Opus audio for robot playback");
            return;
        }
        g_audio_packets.fetch_add(1);
    });
}

std::string make_response_url(const std::string& transcript_url)
{
    const std::size_t path = transcript_url.rfind(kTranscriptPath);
    if (path == std::string::npos) {
        return {};
    }
    return transcript_url.substr(0, path) + kResponsePath;
}

void close_protocol()
{
    std::lock_guard<std::mutex> lock(g_protocol_mutex);
    if (g_protocol != nullptr) {
        g_protocol->CloseAudioChannel(false);
        g_protocol.reset();
    }
    g_connected.store(false);
}

bool open_response_channel()
{
    if (g_opening.exchange(true)) {
        return false;
    }

    Settings settings("websocket", true);
    const std::string transcript_url = settings.GetString("url");
    const std::string response_url = make_response_url(transcript_url);
    if (response_url.empty()) {
        g_opening.store(false);
        return false;
    }

    mclog::tagInfo(kLogTag, "opening warm robot speaker channel at {}", response_url);
    settings.SetString("url", response_url);
    settings.SetString("token", "");
    settings.SetInt("version", 1);

    auto protocol = std::make_unique<WebsocketProtocol>();
    configure_callbacks(*protocol);
    protocol->Start();
    const bool opened = protocol->OpenAudioChannel();

    // The signed-off microphone transport owns the canonical stored URL. Restore
    // it immediately after this second WebSocket has read its response endpoint.
    settings.SetString("url", transcript_url);
    settings.SetString("token", "");
    settings.SetInt("version", 1);

    if (!opened) {
        g_opening.store(false);
        g_connected.store(false);
        g_retry_not_before_us.store(esp_timer_get_time() + kReconnectDelayUs);
        mclog::tagError(
            kLogTag,
            "failed to open robot speaker channel; retrying in 3 seconds");
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(g_protocol_mutex);
        if (g_protocol != nullptr) {
            g_protocol->CloseAudioChannel(false);
        }
        g_protocol = std::move(protocol);
    }

    g_connected.store(true);
    g_opening.store(false);
    return true;
}

void update_thinking_animation(uint32_t now_ms)
{
    if (g_state.load() != ResponseState::Thinking) {
        return;
    }
    if (g_next_thinking_pulse_ms != 0 &&
        static_cast<int32_t>(now_ms - g_next_thinking_pulse_ms) < 0) {
        return;
    }
    g_thinking_green = !g_thinking_green;
    show_frame(g_thinking_green ? g_green_dsc : g_red_dsc);
    g_next_thinking_pulse_ms = now_ms + kThinkingPulseMs;
}

void response_task(void*)
{
    vTaskDelay(pdMS_TO_TICKS(kInitialDelayMs));
    mclog::tagInfo(
        kLogTag,
        "response service started; waiting for the signed-off transcript URL");

    while (true) {
        if (g_close_requested.exchange(false)) {
            close_protocol();
        }

        const int64_t now_us = esp_timer_get_time();
        if (!g_connected.load() && !g_opening.load() &&
            now_us >= g_retry_not_before_us.load()) {
            (void)open_response_channel();
        }

        update_thinking_animation(static_cast<uint32_t>(now_us / 1000));
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

}  // namespace
}  // namespace kadence_voice_response

extern "C" void __attribute__((constructor)) start_kadence_voice_response_service()
{
    const BaseType_t created = xTaskCreate(
        kadence_voice_response::response_task,
        "kade_voice_rx",
        8192,
        nullptr,
        4,
        nullptr);
    if (created != pdPASS) {
        mclog::tagError(
            "KADENCE-VOICE-RX",
            "failed to create robot speaker response task");
    }
}
