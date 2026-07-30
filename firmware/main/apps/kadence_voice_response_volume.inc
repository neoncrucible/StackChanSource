/*
 * Project Kadence Alpha 1 reply-volume wrapper.
 *
 * The proven response transport remains in kadence_voice_response_base.inc.
 * This wrapper adds reply-only volume management while preserving the existing
 * warm WebSocket, decoder queue and optic-eye state behaviour.
 */

#include <algorithm>
#include <audio_codec.h>
#include <board.h>

#define handle_voice_state kadence_base_handle_voice_state
#define configure_callbacks kadence_base_configure_callbacks
#define open_response_channel kadence_base_open_response_channel
#define response_task kadence_base_response_task
#define start_kadence_voice_response_service kadence_base_start_kadence_voice_response_service
#include "kadence_voice_response_base.inc"
#undef start_kadence_voice_response_service
#undef response_task
#undef open_response_channel
#undef configure_callbacks
#undef handle_voice_state

namespace kadence_voice_response {
namespace {

constexpr int kKadenceMinimumReplyVolume = 85;
std::atomic<bool> g_reply_volume_active{false};
std::atomic<int> g_reply_previous_volume{70};

void enable_reply_volume()
{
    AudioCodec* codec = Board::GetInstance().GetAudioCodec();
    if (codec == nullptr) {
        mclog::tagError(kLogTag, "cannot manage Kadence reply volume: audio codec unavailable");
        return;
    }

    const int previous = codec->output_volume();
    const int target = std::max(previous, kKadenceMinimumReplyVolume);
    g_reply_previous_volume.store(previous);

    // Never reduce a board or user volume that is already above the Alpha
    // minimum. The first hardware test revealed this StackChan was already at
    // 95, so the previous fixed value of 85 unintentionally made replies quieter.
    if (target == previous) {
        g_reply_volume_active.store(false);
        mclog::tagInfo(kLogTag,
                       "Kadence reply volume kept at {} (minimum {})",
                       previous,
                       kKadenceMinimumReplyVolume);
        return;
    }

    g_reply_volume_active.store(true);
    codec->SetOutputVolume(target);
    mclog::tagInfo(kLogTag,
                   "Kadence reply volume raised to {} (previous {})",
                   target,
                   previous);
}

void restore_reply_volume()
{
    if (!g_reply_volume_active.exchange(false)) {
        return;
    }

    AudioCodec* codec = Board::GetInstance().GetAudioCodec();
    if (codec == nullptr) {
        return;
    }

    const int previous = g_reply_previous_volume.load();
    codec->SetOutputVolume(previous);
    mclog::tagInfo(kLogTag, "audio volume restored to {} after Kadence reply", previous);
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
        enable_reply_volume();
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
        restore_reply_volume();
        set_state(ResponseState::Idle);
        mclog::tagInfo(
            kLogTag,
            "robot response playback complete after {} Opus packet(s)",
            packets);
    } else if (std::strcmp(state->valuestring, "error") == 0) {
        restore_reply_volume();
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
        restore_reply_volume();
        g_connected.store(false);
        g_close_requested.store(true);
        g_retry_not_before_us.store(esp_timer_get_time() + kReconnectDelayUs);
        mclog::tagError(kLogTag, "robot speaker channel closed; reconnect scheduled");
    });
    protocol.OnNetworkError([](const std::string& message) {
        restore_reply_volume();
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
            restore_reply_volume();
            set_state(ResponseState::Error);
            mclog::tagError(kLogTag, "failed to queue returned Opus audio for robot playback");
            return;
        }
        g_audio_packets.fetch_add(1);
    });
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

void response_task(void*)
{
    vTaskDelay(pdMS_TO_TICKS(kInitialDelayMs));
    mclog::tagInfo(
        kLogTag,
        "response service started; waiting for the signed-off transcript URL");

    while (true) {
        if (g_close_requested.exchange(false)) {
            restore_reply_volume();
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
