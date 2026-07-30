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
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>

namespace kadence_voice_transport {

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
                        mclog::tagInfo(kLogTag, "Wi-Fi connected{}{}",
                                       data.empty() ? "" : " to ", data);
                        break;
                    case NetworkEvent::Disconnected:
                        network_connected_.store(false);
                        mclog::tagError(kLogTag, "Wi-Fi disconnected");
                        if (busy()) {
                            set_error("Wi-Fi disconnected during voice transport");
                        }
                        break;
                    case NetworkEvent::WifiConfigModeEnter:
                        network_connected_.store(false);
                        mclog::tagError(kLogTag,
                                        "Wi-Fi credentials unavailable; device entered configuration mode");
                        break;
                    case NetworkEvent::WifiConfigModeExit:
                        mclog::tagInfo(kLogTag, "Wi-Fi configuration mode exited");
                        break;
                    default:
                        break;
                }
            });

        mclog::tagInfo(kLogTag, "starting stored Wi-Fi connection for transcript transport");
        Board::GetInstance().StartNetwork();
    }

    void notify_send_queue_available()
    {
        send_queue_pending_.store(true);
    }

    bool begin_capture()
    {
        if (audio_service_ == nullptr || open_task_running_.exchange(true)) {
            return false;
        }

        cancel_requested_.store(false);
        capture_active_.store(false);
        finish_pending_.store(false);
        awaiting_transcript_.store(false);
        send_queue_pending_.store(false);
        clear_result_state();
        discard_send_queue();

        const BaseType_t created = xTaskCreate(
            [](void* context) {
                auto* service = static_cast<Service*>(context);
                service->open_capture_task();
                vTaskDelete(nullptr);
            },
            "kade_voice_open",
            8192,
            this,
            4,
            nullptr);

        if (created != pdPASS) {
            open_task_running_.store(false);
            set_error("failed to create voice transport task");
            return false;
        }

        return true;
    }

    void request_transcript()
    {
        if (audio_service_ == nullptr || !capture_active_.load()) {
            set_error("voice capture was not active at timeout");
            return;
        }

        audio_service_->EnableVoiceProcessing(false);
        capture_active_.store(false);
        finish_not_before_us_.store(esp_timer_get_time() + 180000);
        finish_pending_.store(true);
        send_queue_pending_.store(true);
        mclog::tagInfo(kLogTag,
                       "microphone capture stopped; flushing final Opus frames before transcript request");
    }

    void cancel()
    {
        cancel_requested_.store(true);
        finish_pending_.store(false);
        awaiting_transcript_.store(false);
        capture_active_.store(false);

        if (audio_service_ != nullptr) {
            audio_service_->EnableVoiceProcessing(false);
            discard_send_queue();
        }

        close_protocol();
        clear_result_state();
        mclog::tagInfo(kLogTag, "voice transport cancelled and queued microphone audio discarded");
    }

    void complete_session()
    {
        finish_pending_.store(false);
        awaiting_transcript_.store(false);
        capture_active_.store(false);
        close_protocol();
        discard_send_queue();
    }

    void update()
    {
        if (send_queue_pending_.exchange(false) || capture_active_.load() || finish_pending_.load()) {
            drain_send_queue(true);
        }

        if (finish_pending_.load() && esp_timer_get_time() >= finish_not_before_us_.load()) {
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
                mclog::tagInfo(kLogTag, "Opus upload complete; waiting for Windows transcript");
            } else {
                set_error("voice transport closed before transcript request");
            }
        }
    }

    bool take_capture_started()
    {
        return capture_started_event_.exchange(false);
    }

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
        return open_task_running_.load() || capture_active_.load() ||
               finish_pending_.load() || awaiting_transcript_.load() ||
               protocol_open_.load();
    }

    bool network_connected() const
    {
        return network_connected_.load();
    }

private:
    static constexpr const char* kLogTag = "KADENCE-VOICE-NET";
    static constexpr uint16_t kDiscoveryPort = 45872;
    static constexpr const char* kDiscoveryRequest = "KADENCE_DISCOVER_V1";
    static constexpr const char* kDiscoveryReplyPrefix = "KADENCE_SERVER_V1 ";

    AudioService* audio_service_ = nullptr;
    std::unique_ptr<WebsocketProtocol> protocol_;
    std::mutex protocol_mutex_;
    std::mutex result_mutex_;

    std::atomic<bool> network_started_{false};
    std::atomic<bool> network_connected_{false};
    std::atomic<bool> open_task_running_{false};
    std::atomic<bool> cancel_requested_{false};
    std::atomic<bool> protocol_open_{false};
    std::atomic<bool> capture_active_{false};
    std::atomic<bool> finish_pending_{false};
    std::atomic<bool> awaiting_transcript_{false};
    std::atomic<bool> send_queue_pending_{false};
    std::atomic<bool> capture_started_event_{false};
    std::atomic<bool> transcript_ready_{false};
    std::atomic<bool> error_ready_{false};
    std::atomic<int64_t> finish_not_before_us_{0};

    std::string transcript_;
    std::string error_;

    void clear_result_state()
    {
        transcript_ready_.store(false);
        error_ready_.store(false);
        std::lock_guard<std::mutex> lock(result_mutex_);
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

    void set_transcript(const std::string& text)
    {
        {
            std::lock_guard<std::mutex> lock(result_mutex_);
            transcript_ = text;
        }
        transcript_ready_.store(true);
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
                sent = protocol_ != nullptr && protocol_->IsAudioChannelOpened() &&
                       protocol_->SendAudio(std::move(packet));
            }

            if (!sent) {
                if (fail_on_send_error) {
                    set_error("failed to send microphone Opus frame to Windows");
                }
                return false;
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
        for (int attempt = 0; attempt < 150 && !cancel_requested_.load(); ++attempt) {
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
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &allow_broadcast, sizeof(allow_broadcast));

        timeval timeout{};
        timeout.tv_sec = 1;
        timeout.tv_usec = 0;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

        sockaddr_in destination{};
        destination.sin_family = AF_INET;
        destination.sin_port = htons(kDiscoveryPort);
        destination.sin_addr.s_addr = htonl(INADDR_BROADCAST);

        bool discovered = false;
        for (int attempt = 1; attempt <= 5 && !cancel_requested_.load(); ++attempt) {
            mclog::tagInfo(kLogTag, "searching LAN for Kadence transcript server ({}/5)", attempt);
            sendto(sock,
                   kDiscoveryRequest,
                   std::strlen(kDiscoveryRequest),
                   0,
                   reinterpret_cast<sockaddr*>(&destination),
                   sizeof(destination));

            char response[160]{};
            sockaddr_in source{};
            socklen_t source_length = sizeof(source);
            const int received = recvfrom(sock,
                                          response,
                                          sizeof(response) - 1,
                                          0,
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
            if (std::sscanf(reply.c_str(), "KADENCE_SERVER_V1 %u %95s", &port, path) != 2 ||
                port == 0 || port > 65535 || path[0] != '/') {
                continue;
            }

            char address[INET_ADDRSTRLEN]{};
            if (inet_ntop(AF_INET, &source.sin_addr, address, sizeof(address)) == nullptr) {
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
            mclog::tagInfo(kLogTag, "version-1 Opus audio channel opened");
        });
        protocol.OnAudioChannelClosed([this]() {
            protocol_open_.store(false);
            if (!cancel_requested_.load() &&
                (capture_active_.load() || finish_pending_.load() || awaiting_transcript_.load())) {
                set_error("Windows transcript WebSocket disconnected unexpectedly");
            }
        });
        protocol.OnNetworkError([this](const std::string& message) {
            set_error("WebSocket error: " + message);
        });
        protocol.OnIncomingJson([this](const cJSON* root) {
            const cJSON* type = cJSON_GetObjectItem(root, "type");
            if (!cJSON_IsString(type)) {
                return;
            }

            if (std::strcmp(type->valuestring, "stt") == 0) {
                const cJSON* text = cJSON_GetObjectItem(root, "text");
                if (cJSON_IsString(text)) {
                    awaiting_transcript_.store(false);
                    set_transcript(text->valuestring);
                }
            } else if (std::strcmp(type->valuestring, "error") == 0) {
                const cJSON* message = cJSON_GetObjectItem(root, "message");
                set_error(cJSON_IsString(message)
                              ? std::string("Windows transcript error: ") + message->valuestring
                              : "Windows transcript server returned an error");
            }
        });
        protocol.OnIncomingAudio([](std::unique_ptr<AudioStreamPacket>) {
            // Transcript checkpoint is intentionally one-way audio.
        });
    }

    void open_capture_task()
    {
        if (!wait_for_network()) {
            if (!cancel_requested_.load()) {
                set_error("Wi-Fi did not connect before the voice transport timeout");
            }
            open_task_running_.store(false);
            return;
        }

        std::string websocket_url;
        if (!discover_server(websocket_url)) {
            if (!cancel_requested_.load()) {
                set_error("Kadence transcript server was not found on the local network");
            }
            open_task_running_.store(false);
            return;
        }

        mclog::tagInfo(kLogTag, "discovered transcript server at {}", websocket_url);
        {
            Settings settings("websocket", true);
            settings.SetString("url", websocket_url);
            settings.SetString("token", "");
            settings.SetInt("version", 1);
        }

        auto protocol = std::make_unique<WebsocketProtocol>();
        configure_protocol_callbacks(*protocol);
        protocol->Start();

        if (cancel_requested_.load()) {
            open_task_running_.store(false);
            return;
        }

        if (!protocol->OpenAudioChannel()) {
            if (!cancel_requested_.load()) {
                set_error("failed to open the Windows transcript WebSocket");
            }
            open_task_running_.store(false);
            return;
        }

        if (cancel_requested_.load()) {
            protocol->CloseAudioChannel(false);
            open_task_running_.store(false);
            return;
        }

        protocol->SendStartListening(kListeningModeManualStop);
        {
            std::lock_guard<std::mutex> lock(protocol_mutex_);
            protocol_ = std::move(protocol);
        }
        protocol_open_.store(true);
        audio_service_->EnableVoiceProcessing(true);
        capture_active_.store(true);
        capture_started_event_.store(true);
        open_task_running_.store(false);
        mclog::tagInfo(kLogTag, "robot microphone is streaming 16 kHz mono Opus to Windows");
    }
};

}  // namespace kadence_voice_transport
