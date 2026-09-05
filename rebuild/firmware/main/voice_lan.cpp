#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "esp_event.h"
#include "esp_netif.h"
#include "esp_opus_enc.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"

namespace {

constexpr uint16_t kVoiceLanSampleRate = 16000;
constexpr uint16_t kVoiceLanFrameMs = 60;
constexpr std::size_t kVoiceLanMonoFrames = 960;
constexpr std::size_t kVoiceLanStereoSamples = kVoiceLanMonoFrames * 2;
constexpr std::size_t kVoiceLanMaxOpusPacket = 1500;
constexpr std::size_t kVoiceLanEncodedBuffer = 2048;
constexpr uint32_t kVoiceLanMaxPcmReply = 4U * 1024U * 1024U;
constexpr int kVoiceLanConnectTimeoutMs = 15000;
constexpr int kVoiceLanSocketTimeoutSec = 60;
constexpr int kVoiceLanWifiRetries = 3;
constexpr EventBits_t kVoiceLanWifiReadyBit = BIT0;
constexpr EventBits_t kVoiceLanWifiFailedBit = BIT1;

constexpr char kVoiceLanUplinkMagic[4] = {'K', 'D', 'V', '1'};
constexpr char kVoiceLanReplyMagic[4] = {'K', 'D', 'R', '1'};
constexpr char kVoiceLanErrorMagic[4] = {'K', 'D', 'E', '1'};

std::array<int16_t, kVoiceLanStereoSamples> g_voice_lan_stereo{};
std::array<int16_t, kVoiceLanMonoFrames> g_voice_lan_mono{};
std::array<uint8_t, kVoiceLanEncodedBuffer> g_voice_lan_encoded{};
std::array<uint8_t, 4096> g_voice_lan_playback{};

EventGroupHandle_t g_voice_lan_wifi_events = nullptr;
esp_netif_t* g_voice_lan_sta_netif = nullptr;
bool g_voice_lan_wifi_initialised = false;
bool g_voice_lan_wifi_attempt_active = false;
int g_voice_lan_wifi_retry = 0;

struct VoiceLanRequest {
    char request_id[48]{};
    char ssid[33]{};
    char password[64]{};
    char host[46]{};
    uint16_t port = 0;
    uint32_t capture_ms = 0;
};

struct VoiceLanProof {
    bool network = false;
    bool capture = false;
    bool opus = false;
    bool playback = false;
    bool handoff = false;
    bool torque_released = false;

    bool ok() const
    {
        return network && capture && opus && playback && handoff && torque_released;
    }
};

enum class VoiceLanCommandResult : uint8_t {
    NotVoiceTurn = 0,
    Accepted,
    Rejected,
};

void voice_lan_wifi_event(void*, esp_event_base_t event_base, int32_t event_id, void*)
{
    if (g_voice_lan_wifi_events == nullptr) return;

    if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        g_voice_lan_wifi_attempt_active = false;
        xEventGroupSetBits(g_voice_lan_wifi_events, kVoiceLanWifiReadyBit);
        return;
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED &&
        g_voice_lan_wifi_attempt_active) {
        if (g_voice_lan_wifi_retry < kVoiceLanWifiRetries) {
            ++g_voice_lan_wifi_retry;
            (void)esp_wifi_connect();
        } else {
            g_voice_lan_wifi_attempt_active = false;
            xEventGroupSetBits(g_voice_lan_wifi_events, kVoiceLanWifiFailedBit);
        }
    }
}

bool voice_lan_initialise_wifi()
{
    if (g_voice_lan_wifi_initialised) return true;

    esp_err_t err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=netif-init err=%s", esp_err_to_name(err));
        return false;
    }

    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=event-loop err=%s", esp_err_to_name(err));
        return false;
    }

    g_voice_lan_wifi_events = xEventGroupCreate();
    if (g_voice_lan_wifi_events == nullptr) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=event-group");
        return false;
    }

    g_voice_lan_sta_netif = esp_netif_create_default_wifi_sta();
    if (g_voice_lan_sta_netif == nullptr) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=sta-netif");
        return false;
    }

    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&wifi_init);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-init err=%s", esp_err_to_name(err));
        return false;
    }

    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=ram-storage err=%s", esp_err_to_name(err));
        return false;
    }

    err = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &voice_lan_wifi_event, nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-handler err=%s", esp_err_to_name(err));
        return false;
    }
    err = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &voice_lan_wifi_event, nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=ip-handler err=%s", esp_err_to_name(err));
        return false;
    }

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-mode err=%s", esp_err_to_name(err));
        return false;
    }
    err = esp_wifi_start();
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-start err=%s", esp_err_to_name(err));
        return false;
    }
    (void)esp_wifi_set_ps(WIFI_PS_NONE);

    g_voice_lan_wifi_initialised = true;
    ESP_LOGI(kLogTag, "VOICE_LAN wifi=ready storage=ram-only");
    return true;
}

bool voice_lan_connect_wifi(const VoiceLanRequest& request)
{
    if (!voice_lan_initialise_wifi()) return false;

    wifi_config_t config{};
    const std::size_t ssid_len = std::strlen(request.ssid);
    const std::size_t password_len = std::strlen(request.password);
    std::memcpy(config.sta.ssid, request.ssid, ssid_len);
    std::memcpy(config.sta.password, request.password, password_len);
    config.sta.scan_method = WIFI_FAST_SCAN;
    config.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    config.sta.threshold.authmode = WIFI_AUTH_OPEN;

    xEventGroupClearBits(
        g_voice_lan_wifi_events,
        kVoiceLanWifiReadyBit | kVoiceLanWifiFailedBit);
    g_voice_lan_wifi_retry = 0;
    g_voice_lan_wifi_attempt_active = true;

    const esp_err_t disconnect_err = esp_wifi_disconnect();
    if (disconnect_err != ESP_OK && disconnect_err != ESP_ERR_WIFI_NOT_CONNECT) {
        ESP_LOGW(kLogTag, "VOICE_LAN wifi-disconnect err=%s", esp_err_to_name(disconnect_err));
    }

    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &config);
    if (err != ESP_OK) {
        g_voice_lan_wifi_attempt_active = false;
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-config err=%s", esp_err_to_name(err));
        return false;
    }

    err = esp_wifi_connect();
    if (err != ESP_OK) {
        g_voice_lan_wifi_attempt_active = false;
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-connect err=%s", esp_err_to_name(err));
        return false;
    }

    const EventBits_t bits = xEventGroupWaitBits(
        g_voice_lan_wifi_events,
        kVoiceLanWifiReadyBit | kVoiceLanWifiFailedBit,
        pdTRUE,
        pdFALSE,
        pdMS_TO_TICKS(kVoiceLanConnectTimeoutMs));
    g_voice_lan_wifi_attempt_active = false;

    if ((bits & kVoiceLanWifiReadyBit) == 0) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=wifi-ready");
        return false;
    }

    ESP_LOGI(kLogTag, "VOICE_LAN network=connected credentials=persistent-no");
    return true;
}

bool voice_lan_send_all(int sock, const void* raw, std::size_t length)
{
    const auto* data = static_cast<const uint8_t*>(raw);
    std::size_t sent = 0;
    while (sent < length) {
        const int count = send(sock, data + sent, length - sent, 0);
        if (count <= 0) return false;
        sent += static_cast<std::size_t>(count);
    }
    return true;
}

bool voice_lan_recv_all(int sock, void* raw, std::size_t length)
{
    auto* data = static_cast<uint8_t*>(raw);
    std::size_t received = 0;
    while (received < length) {
        const int count = recv(sock, data + received, length - received, 0);
        if (count <= 0) return false;
        received += static_cast<std::size_t>(count);
    }
    return true;
}

int voice_lan_connect_server(const VoiceLanRequest& request)
{
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(request.port);
    if (inet_pton(AF_INET, request.host, &address.sin_addr) != 1) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=host-address");
        return -1;
    }

    const int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=socket");
        return -1;
    }

    timeval timeout{};
    timeout.tv_sec = kVoiceLanSocketTimeoutSec;
    timeout.tv_usec = 0;
    (void)setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    (void)setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

    if (connect(sock, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=tcp-connect");
        close(sock);
        return -1;
    }
    return sock;
}

bool voice_lan_send_hello(int sock)
{
    std::array<uint8_t, 8> hello{};
    std::memcpy(hello.data(), kVoiceLanUplinkMagic, 4);
    const uint16_t sample_rate = htons(kVoiceLanSampleRate);
    const uint16_t frame_ms = htons(kVoiceLanFrameMs);
    std::memcpy(hello.data() + 4, &sample_rate, sizeof(sample_rate));
    std::memcpy(hello.data() + 6, &frame_ms, sizeof(frame_ms));
    return voice_lan_send_all(sock, hello.data(), hello.size());
}

bool voice_lan_send_packet(int sock, const uint8_t* packet, std::size_t length)
{
    if (packet == nullptr || length == 0 || length > kVoiceLanMaxOpusPacket) return false;
    const uint16_t network_length = htons(static_cast<uint16_t>(length));
    return voice_lan_send_all(sock, &network_length, sizeof(network_length)) &&
           voice_lan_send_all(sock, packet, length);
}

bool voice_lan_send_end(int sock)
{
    const uint16_t zero = 0;
    return voice_lan_send_all(sock, &zero, sizeof(zero));
}

bool voice_lan_capture_opus(int sock, uint32_t capture_ms)
{
    esp_opus_enc_config_t opus_config = ESP_OPUS_ENC_CONFIG_DEFAULT();
    opus_config.sample_rate = ESP_AUDIO_SAMPLE_RATE_16K;
    opus_config.channel = ESP_AUDIO_MONO;
    opus_config.bits_per_sample = ESP_AUDIO_BIT16;
    opus_config.bitrate = 24000;
    opus_config.frame_duration = ESP_OPUS_ENC_FRAME_DURATION_60_MS;
    opus_config.application_mode = ESP_OPUS_ENC_APPLICATION_VOIP;
    opus_config.complexity = 2;
    opus_config.enable_fec = false;
    opus_config.enable_dtx = false;
    opus_config.enable_vbr = false;

    void* encoder = nullptr;
    if (esp_opus_enc_open(&opus_config, sizeof(opus_config), &encoder) != ESP_AUDIO_ERR_OK ||
        encoder == nullptr) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=opus-open");
        return false;
    }

    int input_bytes = 0;
    int output_bytes = 0;
    const bool frame_size_ok =
        esp_opus_enc_get_frame_size(encoder, &input_bytes, &output_bytes) == ESP_AUDIO_ERR_OK &&
        input_bytes == static_cast<int>(kVoiceLanMonoFrames * sizeof(int16_t)) &&
        output_bytes > 0 && output_bytes <= static_cast<int>(g_voice_lan_encoded.size());
    if (!frame_size_ok) {
        ESP_LOGE(kLogTag,
                 "VOICE_LAN status=failed stage=opus-frame input=%d output=%d",
                 input_bytes,
                 output_bytes);
        esp_opus_enc_close(encoder);
        return false;
    }

    if (!open_input()) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=input-open");
        esp_opus_enc_close(encoder);
        return false;
    }

    bool ok = true;
    const uint32_t packet_count =
        std::max<uint32_t>(1, (capture_ms + kVoiceLanFrameMs - 1) / kVoiceLanFrameMs);
    for (uint32_t packet_index = 0; packet_index < packet_count; ++packet_index) {
        const esp_err_t read_err = static_cast<esp_err_t>(esp_codec_dev_read(
            g_audio.input_dev,
            g_voice_lan_stereo.data(),
            static_cast<int>(g_voice_lan_stereo.size() * sizeof(int16_t))));
        if (read_err != ESP_OK) {
            ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=capture-read err=%s", esp_err_to_name(read_err));
            ok = false;
            break;
        }

        for (std::size_t frame = 0; frame < kVoiceLanMonoFrames; ++frame) {
            g_voice_lan_mono[frame] = g_voice_lan_stereo[frame * 2];
        }

        esp_audio_enc_in_frame_t input_frame{};
        input_frame.buffer = reinterpret_cast<uint8_t*>(g_voice_lan_mono.data());
        input_frame.len = static_cast<uint32_t>(g_voice_lan_mono.size() * sizeof(int16_t));
        esp_audio_enc_out_frame_t output_frame{};
        output_frame.buffer = g_voice_lan_encoded.data();
        output_frame.len = static_cast<uint32_t>(g_voice_lan_encoded.size());

        if (esp_opus_enc_process(encoder, &input_frame, &output_frame) != ESP_AUDIO_ERR_OK ||
            output_frame.encoded_bytes == 0 ||
            output_frame.encoded_bytes > kVoiceLanMaxOpusPacket ||
            !voice_lan_send_packet(sock, output_frame.buffer, output_frame.encoded_bytes)) {
            ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=opus-send");
            ok = false;
            break;
        }
    }

    if (!close_input()) ok = false;
    esp_opus_enc_close(encoder);

    if (!ok || !voice_lan_send_end(sock)) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=uplink-finish");
        return false;
    }

    ESP_LOGI(kLogTag,
             "VOICE_LAN uplink=complete codec=opus sample_rate=%u frame_ms=%u",
             static_cast<unsigned>(kVoiceLanSampleRate),
             static_cast<unsigned>(kVoiceLanFrameMs));
    return true;
}

bool voice_lan_receive_playback(int sock)
{
    std::array<char, 4> magic{};
    if (!voice_lan_recv_all(sock, magic.data(), magic.size())) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=reply-header");
        return false;
    }

    if (std::memcmp(magic.data(), kVoiceLanErrorMagic, 4) == 0) {
        uint16_t network_length = 0;
        if (voice_lan_recv_all(sock, &network_length, sizeof(network_length))) {
            const uint16_t error_length = ntohs(network_length);
            std::array<uint8_t, 512> discard{};
            std::size_t remaining = std::min<std::size_t>(error_length, discard.size());
            if (remaining > 0) (void)voice_lan_recv_all(sock, discard.data(), remaining);
        }
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=provider");
        return false;
    }

    if (std::memcmp(magic.data(), kVoiceLanReplyMagic, 4) != 0) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=reply-magic");
        return false;
    }

    uint32_t network_pcm_bytes = 0;
    if (!voice_lan_recv_all(sock, &network_pcm_bytes, sizeof(network_pcm_bytes))) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=reply-length");
        return false;
    }
    const uint32_t pcm_bytes = ntohl(network_pcm_bytes);
    if (pcm_bytes == 0 || pcm_bytes > kVoiceLanMaxPcmReply || (pcm_bytes % 2) != 0) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=reply-range bytes=%u", static_cast<unsigned>(pcm_bytes));
        return false;
    }

    if (!open_output()) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=output-open");
        return false;
    }

    bool ok = true;
    const esp_err_t unmute_err = static_cast<esp_err_t>(
        esp_codec_dev_set_out_mute(g_audio.output_dev, false));
    if (unmute_err != ESP_OK) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=output-unmute err=%s", esp_err_to_name(unmute_err));
        ok = false;
    }

    uint32_t remaining = pcm_bytes;
    while (ok && remaining > 0) {
        const std::size_t chunk = std::min<std::size_t>(remaining, g_voice_lan_playback.size());
        if (!voice_lan_recv_all(sock, g_voice_lan_playback.data(), chunk)) {
            ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=reply-read");
            ok = false;
            break;
        }
        const esp_err_t write_err = static_cast<esp_err_t>(esp_codec_dev_write(
            g_audio.output_dev,
            g_voice_lan_playback.data(),
            static_cast<int>(chunk)));
        if (write_err != ESP_OK) {
            ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=playback-write err=%s", esp_err_to_name(write_err));
            ok = false;
            break;
        }
        remaining -= static_cast<uint32_t>(chunk);
    }

    if (ok) {
        const esp_err_t silence_err = static_cast<esp_err_t>(esp_codec_dev_write(
            g_audio.output_dev,
            g_silence.data(),
            static_cast<int>(g_silence.size() * sizeof(int16_t))));
        if (silence_err != ESP_OK) {
            ESP_LOGW(kLogTag, "VOICE_LAN silence-write err=%s", esp_err_to_name(silence_err));
        }
    }

    if (!close_output()) ok = false;
    if (ok) {
        ESP_LOGI(kLogTag, "VOICE_LAN downlink=complete codec=pcm16 sample_rate=%u", static_cast<unsigned>(kVoiceLanSampleRate));
    }
    return ok;
}

VoiceLanProof voice_lan_run_turn(const VoiceLanRequest& request)
{
    VoiceLanProof proof{};

    if (!g_audio.ready || g_audio.input_dev == nullptr || g_audio.output_dev == nullptr) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=audio-transport");
        return proof;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "VOICE_LAN status=failed stage=torque-precondition");
        return proof;
    }

    presence_interaction_begin();
    presentation_set_state(PresentationState::Attentive, "voice-lan-connect");

    if (!voice_lan_connect_wifi(request)) {
        presentation_set_state(PresentationState::Degraded, "voice-lan-network");
        vTaskDelay(pdMS_TO_TICKS(180));
        presentation_set_state(PresentationState::Idle, "voice-lan-failed");
        presence_interaction_end();
        proof.torque_released = p9_release_torque() && p10_verify_torque_released();
        return proof;
    }
    proof.network = true;

    const int sock = voice_lan_connect_server(request);
    if (sock < 0 || !voice_lan_send_hello(sock)) {
        if (sock >= 0) close(sock);
        presentation_set_state(PresentationState::Degraded, "voice-lan-server");
        vTaskDelay(pdMS_TO_TICKS(180));
        presentation_set_state(PresentationState::Idle, "voice-lan-failed");
        presence_interaction_end();
        proof.torque_released = p9_release_torque() && p10_verify_torque_released();
        return proof;
    }

    presentation_set_state(PresentationState::Listening, "voice-lan-capture");
    proof.capture = true;
    proof.opus = voice_lan_capture_opus(sock, request.capture_ms);
    if (!proof.opus) {
        close(sock);
        presentation_set_state(PresentationState::Degraded, "voice-lan-uplink");
        vTaskDelay(pdMS_TO_TICKS(180));
        presentation_set_state(PresentationState::Idle, "voice-lan-failed");
        presence_interaction_end();
        proof.capture = false;
        proof.torque_released = p9_release_torque() && p10_verify_torque_released();
        return proof;
    }

    presentation_set_state(PresentationState::Thinking, "voice-lan-provider");
    presentation_set_state(PresentationState::Speaking, "voice-lan-playback");
    proof.playback = voice_lan_receive_playback(sock);
    close(sock);

    proof.handoff = proof.capture && proof.opus && proof.playback;
    proof.torque_released = p9_release_torque() && p10_verify_torque_released();

    if (proof.ok()) {
        presentation_set_state(PresentationState::Idle, "voice-lan-complete");
        ESP_LOGI(kLogTag,
                 "VOICE_LAN status=complete network=1 capture=1 opus=1 playback=1 handoff=1 torque=released");
    } else {
        presentation_set_state(PresentationState::Degraded, "voice-lan-playback-failed");
        vTaskDelay(pdMS_TO_TICKS(180));
        presentation_set_state(PresentationState::Idle, "voice-lan-failed");
    }
    presence_interaction_end();
    return proof;
}

bool voice_lan_make_ack(const VoiceLanRequest& request,
                        const VoiceLanProof& proof,
                        char* output,
                        size_t output_size)
{
    if (request.request_id[0] == '\0' || output == nullptr || output_size == 0) return false;

    cJSON* root = cJSON_CreateObject();
    cJSON* payload = cJSON_CreateObject();
    if (root == nullptr || payload == nullptr) {
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    bool built = true;
    built = built && cJSON_AddNumberToObject(root, "v", 1) != nullptr;
    built = built && cJSON_AddStringToObject(root, "id", request.request_id) != nullptr;
    built = built && cJSON_AddStringToObject(root, "ts", "device") != nullptr;
    built = built && cJSON_AddStringToObject(root, "kind", "ack") != nullptr;
    built = built && cJSON_AddStringToObject(root, "name", "voice.turn") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", proof.ok()) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "network", proof.network) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "capture", proof.capture) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "opus", proof.opus) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "playback", proof.playback) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "handoff", proof.handoff) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "torque_released", proof.torque_released) != nullptr;
    if (built) {
        cJSON_AddItemToObject(root, "payload", payload);
        payload = nullptr;
    }

    char* rendered = built ? cJSON_PrintUnformatted(root) : nullptr;
    if (rendered == nullptr || std::strlen(rendered) >= output_size) {
        cJSON_free(rendered);
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }
    std::snprintf(output, output_size, "%s", rendered);
    cJSON_free(rendered);
    cJSON_Delete(root);
    return true;
}

VoiceLanCommandResult voice_lan_execute_command(const char* raw,
                                                char* ack,
                                                size_t ack_size)
{
    if (raw == nullptr) return VoiceLanCommandResult::NotVoiceTurn;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return VoiceLanCommandResult::NotVoiceTurn;
    }

    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name) || name->valuestring == nullptr ||
        std::strcmp(name->valuestring, "voice.turn") != 0) {
        cJSON_Delete(root);
        return VoiceLanCommandResult::NotVoiceTurn;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* ssid = payload ? cJSON_GetObjectItemCaseSensitive(payload, "ssid") : nullptr;
    const cJSON* password = payload ? cJSON_GetObjectItemCaseSensitive(payload, "password") : nullptr;
    const cJSON* host = payload ? cJSON_GetObjectItemCaseSensitive(payload, "host") : nullptr;
    const cJSON* port = payload ? cJSON_GetObjectItemCaseSensitive(payload, "port") : nullptr;
    const cJSON* capture_ms = payload ? cJSON_GetObjectItemCaseSensitive(payload, "capture_ms") : nullptr;

    const bool fields_valid =
        cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
        cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
        request_id->valuestring[0] != '\0' &&
        cJSON_IsString(kind) && kind->valuestring != nullptr &&
        std::strcmp(kind->valuestring, "command") == 0 &&
        cJSON_IsObject(payload) &&
        cJSON_IsString(ssid) && ssid->valuestring != nullptr &&
        cJSON_IsString(password) && password->valuestring != nullptr &&
        cJSON_IsString(host) && host->valuestring != nullptr &&
        cJSON_IsNumber(port) && port->valuedouble == static_cast<double>(port->valueint) &&
        cJSON_IsNumber(capture_ms) && capture_ms->valuedouble == static_cast<double>(capture_ms->valueint);

    if (!fields_valid) {
        cJSON_Delete(root);
        return VoiceLanCommandResult::Rejected;
    }

    const std::size_t id_len = std::strlen(request_id->valuestring);
    const std::size_t ssid_len = std::strlen(ssid->valuestring);
    const std::size_t password_len = std::strlen(password->valuestring);
    const std::size_t host_len = std::strlen(host->valuestring);
    if (id_len == 0 || id_len >= 48 ||
        ssid_len == 0 || ssid_len > 32 ||
        password_len > 63 ||
        host_len == 0 || host_len >= 46 ||
        port->valueint < 1 || port->valueint > 65535 ||
        capture_ms->valueint < 2400 || capture_ms->valueint > 8000) {
        cJSON_Delete(root);
        return VoiceLanCommandResult::Rejected;
    }

    VoiceLanRequest request{};
    std::snprintf(request.request_id, sizeof(request.request_id), "%s", request_id->valuestring);
    std::memcpy(request.ssid, ssid->valuestring, ssid_len);
    std::memcpy(request.password, password->valuestring, password_len);
    std::snprintf(request.host, sizeof(request.host), "%s", host->valuestring);
    request.port = static_cast<uint16_t>(port->valueint);
    request.capture_ms = static_cast<uint32_t>(capture_ms->valueint);
    cJSON_Delete(root);

    const VoiceLanProof proof = voice_lan_run_turn(request);
    if (!voice_lan_make_ack(request, proof, ack, ack_size)) {
        return VoiceLanCommandResult::Rejected;
    }
    return VoiceLanCommandResult::Accepted;
}

}  // namespace
