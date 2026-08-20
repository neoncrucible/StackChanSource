#pragma once

#include <audio_service.h>
#include <board.h>
#include <cJSON.h>
#include <mooncake_log.h>
#include <settings.h>
#include <websocket_protocol.h>

#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <lwip/inet.h>
#include <lwip/sockets.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>

namespace kadence_voice_transport {

// Kadence 2.0 Alpha 1 transport.
//
// The Beta transport already used Xiaozhi's WebsocketProtocol for a warm,
// version-1 Opus uplink to the Windows transcript service. Alpha 1 keeps that
// proven network/microphone path but now consumes Xiaozhi's native downstream
// TTS audio as well. Kadence-specific server control messages use a small,
// versioned JSON namespace alongside Xiaozhi protocol messages; the endpoint
// event only asks the robot to execute its existing clean stop/flush path.
// The existing UI state machine still waits for a "transcript" result, which is
// deliberately published only after STT exists, TTS has stopped and the
// AudioService playback queues have drained.
class Service {
public:
    void initialise(AudioService* audio_service)
    {
        audio_service_ = audio_service;
    }

    void start_network()
    {
        if (network_started_.exchange(true)) {
            return;
        }

        // Prime the microphone processor once after boot so its first-use cost is
        // outside the speaking window. Beta's main loop may park AFE afterwards;
        // the initialisation remains warm.
        ensure_processor_primed();

        Board::GetInstance().SetNetworkEventCallback(
            [this](NetworkEvent event, const std::string& data) {
                switch (event) {
                    case NetworkEvent::Scanning:
                        mclog::tagInfo(kLogTag, "Wi-Fi scan started");
                        break;
                    case NetworkEvent::Connecting:
                        mclog::tagInfo(kLogTag, "Wi-Fi connecting{}{}",
                                       data.empty() ? "" : " to ", data);
                        break;
                    case NetworkEvent::Connected:
                        network_connected_.store(true);
                        prepare_requested_.store(true);
                        retry_not_before_us_.store(0);
                        mclog::tagInfo(kLogTag, "Wi-Fi connected{}{}",
                                       data.empty() ? "" : " to ", data);
                        break;
                    case NetworkEvent::Disconnected:
                        network_connected_.store(false);
                        protocol_open_.store(false);
                        close_requested_.store(true);
                        mclog::tagError(kLogTag, "Wi-Fi disconnected");
                        if (session_active()) {
                            set_error("Wi-Fi disconnected during Kadence 2.0 voice turn");
                        }
                        break;
                    case NetworkEvent::WifiConfigModeEnter:
                        network_connected_.store(false);
                        protocol_open_.store(false);
                        close_requested_.store(true);
                        mclog::tagError(
                            kLogTag,
                            "Wi-Fi credentials unavailable; device entered configuration mode");
                        break;
                    case NetworkEvent::WifiConfigModeExit:
                        mclog::tagInfo(kLogTag, "Wi-Fi configuration mode exited");
                        break;
                    default:
                        break;
                }
            });

        mclog::tagInfo(kLogTag,
                       "starting stored Wi-Fi connection and warm Kadence 2.0 transport");
        Board::GetInstance().StartNetwork();
    }

    void notify_send_queue_available()
    {
        send_queue_pending_.store(true);
    }

    bool begin_capture()
    {
        if (audio_service_ == nullptr || !processor_primed_.load() ||
            open_task_running_.load() || session_active() ||
            !protocol_open_.load()) {
            prepare_requested_.store(network_connected_.load());
            return false;
        }

        clear_turn_state();
        discard_send_queue();
        finish_pending_.store(false);
        send_queue_pending_.store(false);
        capture_started_event_.store(false);

        bool channel_ready = false;
        {
            std::lock_guard<std::mutex> lock(protocol_mutex_);
            if (protocol_ != nullptr && protocol_->IsAudioChannelOpened()) {
                protocol_->SendStartListening(kListeningModeManualStop);
                channel_ready = true;
            }
        }

        if (!channel_ready) {
            protocol_open_.store(false);
            close_requested_.store(true);
            prepare_requested_.store(network_connected_.load());
            return false;
        }

        // Everything in the send queue before this point belongs to idle/chirp.
        discard_send_queue();
        capture_active_.store(true);
        capture_started_event_.store(true);
        mclog::tagInfo(kLogTag,
                       "Kadence 2.0 warm channel accepted capture start");
        mclog::tagInfo(kLogTag,
                       "primed microphone streaming 16 kHz mono Opus to Xiaozhi backend");
        return true;
    }

    void request_transcript()
    {
        if (audio_service_ == nullptr || !capture_active_.load()) {
            set_error("voice capture was not active at end of speech");
            return;
        }

        capture_active_.store(false);
        server_endpoint_requested_.store(false);
        finish_not_before_us_.store(esp_timer_get_time() + kFinalOpusFlushUs);
        finish_pending_.store(true);
        send_queue_pending_.store(true);
        response_pending_.store(true);
        mclog::tagInfo(kLogTag,
                       "K2 LATENCY T2 end-of-speech at {} us; flushing final Opus",
                       esp_timer_get_time());
    }

    void cancel()
    {
        const bool server_session_started = session_active();

        finish_pending_.store(false);
        awaiting_transcript_.store(false);
        capture_active_.store(false);
        response_pending_.store(false);
        capture_started_event_.store(false);
        server_endpoint_requested_.store(false);
        send_queue_pending_.store(false);
        discard_send_queue();

        if (audio_service_ != nullptr) {
            // A head swipe during a spoken reply must stop queued TTS immediately.
            audio_service_->ResetDecoder();
        }

        clear_turn_state();

        if (server_session_started) {
            // Closing the protocol cleanly abandons the server-side turn. A warm
            // reconnect is prepared as soon as the robot returns to idle.
            protocol_open_.store(false);
            close_requested_.store(true);
            prepare_requested_.store(network_connected_.load());
            retry_not_before_us_.store(0);
            mclog::tagInfo(kLogTag,
                           "Kadence 2.0 voice turn cancelled; warm reconnect scheduled");
        } else {
            mclog::tagInfo(kLogTag,
                           "voice cue cancelled before server turn; microphone remains primed");
        }
    }

    void complete_session()
    {
        finish_pending_.store(false);
        awaiting_transcript_.store(false);
        capture_active_.store(false);
        response_pending_.store(false);
        server_endpoint_requested_.store(false);
        discard_send_queue();
        reset_response_flags();

        if (!protocol_open_.load()) {
            prepare_requested_.store(network_connected_.load());
        } else {
            mclog::tagInfo(kLogTag,
                           "Kadence 2.0 turn complete; warm WebSocket remains ready");
        }
    }

    void update()
    {
        if (close_requested_.exchange(false)) {
            close_protocol();
        }

        if (capture_active_.load() || finish_pending_.load()) {
            if (send_queue_pending_.exchange(false) || capture_active_.load() ||
                finish_pending_.load()) {
                drain_send_queue(true);
            }
        } else if (processor_primed_.load()) {
            // Never leak idle/chirp frames onto the wire.
            send_queue_pending_.store(false);
            discard_send_queue();
        }

        if (finish_pending_.load() &&
            esp_timer_get_time() >= finish_not_before_us_.load()) {
            drain_send_queue(true);

            bool sent = false;
            {
                std::lock_guard<std::mutex> lock(protocol_mutex_);
                if (protocol_ != nullptr && protocol_->IsAudioChannelOpened()) {
                    protocol_->SendStopListening();
                    sent = true;
                }
            }

            finish_pending_.store(false);
            if (sent) {
                awaiting_transcript_.store(true);
                response_pending_.store(true);
                mclog::tagInfo(kLogTag,
                               "final Opus uploaded; Xiaozhi turn processing continues on warm socket");
            } else {
                protocol_open_.store(false);
                close_requested_.store(true);
                prepare_requested_.store(network_connected_.load());
                set_error("voice transport closed before stop-listening request");
            }
        }

        publish_turn_complete_when_playback_drained();

        const int64_t now_us = esp_timer_get_time();
        if (network_connected_.load() && prepare_requested_.load() &&
            !protocol_open_.load() && !open_task_running_.load() &&
            !session_active() && now_us >= retry_not_before_us_.load()) {
            start_prepare_task();
        }
    }

    bool take_capture_started()
    {
        return capture_started_event_.exchange(false);
    }

    bool take_server_endpoint()
    {
        return server_endpoint_requested_.exchange(false);
    }

    // Compatibility contract with the proven Beta UI state machine. In 2.0
    // Alpha 1 this becomes ready only after STT + TTS + playback drain are done.
    bool take_transcript(std::string& transcript)
    {
        if (!transcript_ready_.exchange(false)) {
            return false;
        }
        std::lock_guard<std::mutex> lock(result_mutex_);
        transcript = transcript_;
        return true;
    }

    bool take_error(std::string& error)
    {
        if (!error_ready_.exchange(false)) {
            return false;
        }
        std::lock_guard<std::mutex> lock(result_mutex_);
        error = error_;
        return true;
    }

    bool busy() const
    {
        return open_task_running_.load() || session_active();
    }

    bool ready() const
    {
        return processor_primed_.load() && protocol_open_.load();
    }

    bool network_connected() const
    {
        return network_connected_.load();
    }

private:
    static constexpr const char* kLogTag = "KADENCE-2-VOICE";
    static constexpr uint16_t kDiscoveryPort = 45872;
    static constexpr const char* kDiscoveryRequest = "KADENCE_DISCOVER_V1";
    static constexpr const char* kDiscoveryReplyPrefix = "KADENCE_SERVER_V1 ";
    static constexpr int64_t kReconnectDelayUs = 3000000;
    static constexpr int64_t kFinalOpusFlushUs = 180000;
    static constexpr int64_t kTtsDrainGuardUs = 150000;

    AudioService* audio_service_ = nullptr;
    std::unique_ptr<WebsocketProtocol> protocol_;
    std::mutex protocol_mutex_;
    std::mutex result_mutex_;

    std::atomic<bool> network_started_{false};
    std::atomic<bool> network_connected_{false};
    std::atomic<bool> processor_primed_{false};
    std::atomic<bool> prepare_requested_{false};
    std::atomic<bool> open_task_running_{false};
    std::atomic<bool> close_requested_{false};
    std::atomic<bool> protocol_open_{false};
    std::atomic<bool> capture_active_{false};
    std::atomic<bool> finish_pending_{false};
    std::atomic<bool> awaiting_transcript_{false};
    std::atomic<bool> response_pending_{false};
    std::atomic<bool> send_queue_pending_{false};
    std::atomic<bool> capture_started_event_{false};
    std::atomic<bool> server_endpoint_requested_{false};
    std::atomic<bool> transcript_ready_{false};
    std::atomic<bool> error_ready_{false};
    std::atomic<bool> stt_received_{false};
    std::atomic<bool> tts_started_{false};
    std::atomic<bool> tts_stopped_{false};
    std::atomic<bool> first_uplink_seen_{false};
    std::atomic<bool> first_tts_audio_seen_{false};
    std::atomic<bool> turn_complete_published_{false};
    std::atomic<int64_t> finish_not_before_us_{0};
    std::atomic<int64_t> retry_not_before_us_{0};
    std::atomic<int64_t> tts_drain_not_before_us_{0};

    std::string pending_transcript_;
    std::string transcript_;
    std::string error_;

    bool session_active() const
    {
        return capture_active_.load() || finish_pending_.load() ||
               awaiting_transcript_.load() || response_pending_.load();
    }

    void ensure_processor_primed()
    {
        if (audio_service_ == nullptr || processor_primed_.exchange(true)) {
            return;
        }

        audio_service_->EnableVoiceProcessing(true);
        discard_send_queue();
        mclog::tagInfo(kLogTag,
                       "microphone processor primed; pre-wake audio will be discarded");
    }

    void reset_response_flags()
    {
        stt_received_.store(false);
        tts_started_.store(false);
        tts_stopped_.store(false);
        first_uplink_seen_.store(false);
        first_tts_audio_seen_.store(false);
        turn_complete_published_.store(false);
        tts_drain_not_before_us_.store(0);
    }

    void clear_turn_state()
    {
        transcript_ready_.store(false);
        error_ready_.store(false);
        awaiting_transcript_.store(false);
        response_pending_.store(false);
        server_endpoint_requested_.store(false);
        reset_response_flags();
        std::lock_guard<std::mutex> lock(result_mutex_);
        pending_transcript_.clear();
        transcript_.clear();
        error_.clear();
    }

    void set_error(const std::string& message)
    {
        {
            std::lock_guard<std::mutex> lock(result_mutex_);
            error_ = message;
        }
        error_ready_.store(true);
        mclog::tagError(kLogTag, "{}", message);
    }

    void store_stt(const std::string& text)
    {
        {
            std::lock_guard<std::mutex> lock(result_mutex_);
            pending_transcript_ = text;
        }
        stt_received_.store(true);
        awaiting_transcript_.store(false);
        response_pending_.store(true);
        mclog::tagInfo(kLogTag,
                       "K2 LATENCY T3 STT ready at {} us: {}",
                       esp_timer_get_time(),
                       text.empty() ? "<no speech recognised>" : text);
    }

    void publish_turn_complete_when_playback_drained()
    {
        if (!response_pending_.load() || !stt_received_.load() ||
            !tts_stopped_.load() || turn_complete_published_.load() ||
            audio_service_ == nullptr) {
            return;
        }

        const int64_t guard = tts_drain_not_before_us_.load();
        if (guard != 0 && esp_timer_get_time() < guard) {
            return;
        }

        if (!audio_service_->IsIdle()) {
            return;
        }

        {
            std::lock_guard<std::mutex> lock(result_mutex_);
            transcript_ = pending_transcript_;
        }
        turn_complete_published_.store(true);
        transcript_ready_.store(true);
        mclog::tagInfo(kLogTag,
                       "TTS playback drained; releasing completed turn to Kadence UI");
    }

    void discard_send_queue()
    {
        if (audio_service_ == nullptr) {
            return;
        }
        while (audio_service_->PopPacketFromSendQueue() != nullptr) {
        }
    }

    bool drain_send_queue(bool fail_on_send_error)
    {
        if (audio_service_ == nullptr) {
            return false;
        }

        while (auto packet = audio_service_->PopPacketFromSendQueue()) {
            bool sent = false;
            {
                std::lock_guard<std::mutex> lock(protocol_mutex_);
                sent = protocol_ != nullptr &&
                       protocol_->IsAudioChannelOpened() &&
                       protocol_->SendAudio(std::move(packet));
            }

            if (!sent) {
                protocol_open_.store(false);
                close_requested_.store(true);
                prepare_requested_.store(network_connected_.load());
                if (fail_on_send_error) {
                    set_error("failed to send microphone Opus frame to Xiaozhi backend");
                }
                return false;
            }

            if (!first_uplink_seen_.exchange(true)) {
                mclog::tagInfo(kLogTag,
                               "K2 LATENCY T1 first microphone Opus sent at {} us",
                               esp_timer_get_time());
            }
        }
        return true;
    }

    void close_protocol()
    {
        std::lock_guard<std::mutex> lock(protocol_mutex_);
        if (protocol_ != nullptr) {
            protocol_->CloseAudioChannel(false);
            protocol_.reset();
        }
        protocol_open_.store(false);
    }

    bool wait_for_network()
    {
        for (int attempt = 0; attempt < 150; ++attempt) {
            if (network_connected_.load()) {
                return true;
            }
            vTaskDelay(pdMS_TO_TICKS(100));
        }
        return false;
    }

    bool discover_server(std::string& websocket_url)
    {
        const int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock < 0) {
            return false;
        }

        int allow_broadcast = 1;
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &allow_broadcast,
                   sizeof(allow_broadcast));

        timeval timeout{};
        timeout.tv_sec = 1;
        timeout.tv_usec = 0;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

        sockaddr_in destination{};
        destination.sin_family = AF_INET;
        destination.sin_port = htons(kDiscoveryPort);
        destination.sin_addr.s_addr = htonl(INADDR_BROADCAST);

        bool discovered = false;
        for (int attempt = 1; attempt <= 5; ++attempt) {
            if (!network_connected_.load()) {
                break;
            }

            mclog::tagInfo(kLogTag,
                           "searching LAN for Kadence 2.0 backend ({}/5)", attempt);
            sendto(sock, kDiscoveryRequest, std::strlen(kDiscoveryRequest), 0,
                   reinterpret_cast<sockaddr*>(&destination), sizeof(destination));

            char response[160]{};
            sockaddr_in source{};
            socklen_t source_length = sizeof(source);
            const int received = recvfrom(sock, response, sizeof(response) - 1, 0,
                                          reinterpret_cast<sockaddr*>(&source),
                                          &source_length);
            if (received <= 0) {
                continue;
            }
            response[received] = '\0';

            const std::string reply(response);
            if (reply.rfind(kDiscoveryReplyPrefix, 0) != 0) {
                continue;
            }

            unsigned int port = 0;
            char path[96]{};
            if (std::sscanf(reply.c_str(), "KADENCE_SERVER_V1 %u %95s",
                            &port, path) != 2 ||
                port == 0 || port > 65535 || path[0] != '/') {
                continue;
            }

            char address[INET_ADDRSTRLEN]{};
            if (inet_ntop(AF_INET, &source.sin_addr, address,
                          sizeof(address)) == nullptr) {
                continue;
            }

            websocket_url = "ws://" + std::string(address) + ":" +
                            std::to_string(port) + path;
            discovered = true;
            break;
        }

        close(sock);
        return discovered;
    }

    void configure_protocol_callbacks(WebsocketProtocol& protocol)
    {
        protocol.OnConnected([]() {
            mclog::tagInfo(kLogTag, "WebSocket connected");
        });
        protocol.OnAudioChannelOpened([]() {
            mclog::tagInfo(kLogTag,
                           "Xiaozhi version-1 bidirectional Opus channel opened");
        });
        protocol.OnAudioChannelClosed([this]() {
            protocol_open_.store(false);
            close_requested_.store(true);
            prepare_requested_.store(network_connected_.load());
            if (session_active()) {
                set_error("Kadence 2.0 WebSocket disconnected unexpectedly");
            } else {
                mclog::tagError(kLogTag,
                                "warm WebSocket disconnected; reconnect scheduled");
            }
        });
        protocol.OnNetworkError([this](const std::string& message) {
            protocol_open_.store(false);
            close_requested_.store(true);
            prepare_requested_.store(network_connected_.load());
            if (session_active()) {
                set_error("WebSocket error: " + message);
            } else {
                mclog::tagError(kLogTag,
                                "warm WebSocket error: {}; reconnect scheduled",
                                message);
            }
        });

        protocol.OnIncomingJson([this](const cJSON* root) {
            const cJSON* type = cJSON_GetObjectItem(root, "type");
            if (!cJSON_IsString(type)) {
                return;
            }

            if (std::strcmp(type->valuestring, "kadence") == 0) {
                const cJSON* version = cJSON_GetObjectItem(root, "version");
                const cJSON* event = cJSON_GetObjectItem(root, "event");
                if (!cJSON_IsNumber(version) || version->valueint != 1 ||
                    !cJSON_IsString(event)) {
                    mclog::tagInfo(kLogTag,
                                   "ignored malformed/unsupported Kadence control message");
                    return;
                }

                if (std::strcmp(event->valuestring, "endpoint") == 0) {
                    if (capture_active_.load()) {
                        server_endpoint_requested_.store(true);
                        mclog::tagInfo(kLogTag,
                                       "Kadence control endpoint request received");
                    }
                    return;
                }

                // Unknown version-1 Kadence controls are deliberately ignored so
                // future server features cannot accidentally alter Alpha motion
                // or device state.
                return;
            }

            if (std::strcmp(type->valuestring, "stt") == 0) {
                const cJSON* text = cJSON_GetObjectItem(root, "text");
                if (cJSON_IsString(text)) {
                    store_stt(text->valuestring);
                }
                return;
            }

            if (std::strcmp(type->valuestring, "tts") == 0) {
                const cJSON* state = cJSON_GetObjectItem(root, "state");
                if (!cJSON_IsString(state)) {
                    return;
                }

                if (std::strcmp(state->valuestring, "start") == 0) {
                    tts_started_.store(true);
                    response_pending_.store(true);
                    mclog::tagInfo(kLogTag,
                                   "Xiaozhi TTS stream started at {} us",
                                   esp_timer_get_time());
                } else if (std::strcmp(state->valuestring, "sentence_start") == 0) {
                    const cJSON* text = cJSON_GetObjectItem(root, "text");
                    if (cJSON_IsString(text)) {
                        mclog::tagInfo(kLogTag, "KADENCE RESPONSE: {}", text->valuestring);
                    }
                } else if (std::strcmp(state->valuestring, "stop") == 0) {
                    tts_stopped_.store(true);
                    tts_drain_not_before_us_.store(
                        esp_timer_get_time() + kTtsDrainGuardUs);
                    mclog::tagInfo(kLogTag,
                                   "Xiaozhi TTS stream stopped; waiting for device playback drain");
                }
                return;
            }

            if (std::strcmp(type->valuestring, "error") == 0) {
                const cJSON* message = cJSON_GetObjectItem(root, "message");
                set_error(cJSON_IsString(message)
                              ? std::string("Xiaozhi backend error: ") + message->valuestring
                              : "Xiaozhi backend returned an error");
                return;
            }

            if (std::strcmp(type->valuestring, "llm") == 0) {
                // Emotion mapping arrives in a later 2.0 gate. Do not let model
                // output directly control robot movement in Alpha 1.
                return;
            }

            if (std::strcmp(type->valuestring, "mcp") == 0) {
                // MCP is intentionally ignored until safe Kadence tool schemas
                // are defined. Raw model-directed motion is never accepted.
                return;
            }

            if (std::strcmp(type->valuestring, "keepalive") == 0) {
                return;
            }
        });

        protocol.OnIncomingAudio([this](std::unique_ptr<AudioStreamPacket> packet) {
            if (audio_service_ == nullptr || packet == nullptr) {
                return;
            }

            response_pending_.store(true);
            if (!audio_service_->PushPacketToDecodeQueue(std::move(packet))) {
                set_error("Kadence TTS decode queue overflow");
                return;
            }

            if (!first_tts_audio_seen_.exchange(true)) {
                mclog::tagInfo(kLogTag,
                               "K2 LATENCY T7 first TTS Opus queued at {} us",
                               esp_timer_get_time());
            }
        });
    }

    void start_prepare_task()
    {
        if (open_task_running_.exchange(true)) {
            return;
        }

        prepare_requested_.store(false);
        const BaseType_t created = xTaskCreate(
            [](void* context) {
                auto* service = static_cast<Service*>(context);
                service->prepare_connection_task();
                vTaskDelete(nullptr);
            },
            "kade2_voice_warm",
            8192,
            this,
            4,
            nullptr);

        if (created != pdPASS) {
            open_task_running_.store(false);
            schedule_prepare_retry("failed to create warm voice transport task");
        }
    }

    void schedule_prepare_retry(const char* message)
    {
        protocol_open_.store(false);
        prepare_requested_.store(true);
        retry_not_before_us_.store(esp_timer_get_time() + kReconnectDelayUs);
        mclog::tagError(kLogTag,
                        "{}; retrying warm connection in 3 seconds", message);
    }

    void prepare_connection_task()
    {
        if (!wait_for_network()) {
            open_task_running_.store(false);
            schedule_prepare_retry(
                "Wi-Fi did not connect before warm transport timeout");
            return;
        }

        std::string websocket_url;
        if (!discover_server(websocket_url)) {
            open_task_running_.store(false);
            schedule_prepare_retry(
                "Kadence 2.0 backend was not found on the local network");
            return;
        }

        mclog::tagInfo(kLogTag,
                       "discovered Kadence 2.0 backend at {} during idle warm-up",
                       websocket_url);
        {
            Settings settings("websocket", true);
            settings.SetString("url", websocket_url);
            settings.SetString("token", "");
            settings.SetInt("version", 1);
        }

        auto protocol = std::make_unique<WebsocketProtocol>();
        configure_protocol_callbacks(*protocol);
        protocol->Start();

        if (!protocol->OpenAudioChannel()) {
            open_task_running_.store(false);
            schedule_prepare_retry(
                "failed to open warm Xiaozhi WebSocket");
            return;
        }

        if (!network_connected_.load()) {
            protocol->CloseAudioChannel(false);
            open_task_running_.store(false);
            schedule_prepare_retry(
                "Wi-Fi disconnected while warming Kadence 2.0 transport");
            return;
        }

        {
            std::lock_guard<std::mutex> lock(protocol_mutex_);
            if (protocol_ != nullptr) {
                protocol_->CloseAudioChannel(false);
            }
            protocol_ = std::move(protocol);
        }

        protocol_open_.store(true);
        retry_not_before_us_.store(0);
        open_task_running_.store(false);
        mclog::tagInfo(kLogTag,
                       "Kadence 2.0 bidirectional transport standing by");
    }
};

}  // namespace kadence_voice_transport
