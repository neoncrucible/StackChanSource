#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

constexpr std::size_t kDeviceAudioCheckFrames = 24000;  // 1.5 s at 16 kHz.
constexpr std::size_t kDeviceAudioReadFrames = 960;    // 60 ms at 16 kHz.
constexpr int kDeviceAudioCueMs = 350;

std::array<int16_t, kDeviceAudioCheckFrames> g_device_audio_check_mono{};
std::array<int16_t, kDeviceAudioReadFrames * 2> g_device_audio_check_stereo{};

enum class DeviceAudioCommandResult : uint8_t {
    NotDeviceAudio = 0,
    Accepted,
    Rejected,
};

bool device_audio_capture_check_sample()
{
    if (!g_audio.ready || g_audio.input_dev == nullptr) return false;
    if (!open_input()) return false;

    bool ok = true;
    std::size_t captured = 0;
    while (captured < g_device_audio_check_mono.size()) {
        const std::size_t frames =
            std::min(kDeviceAudioReadFrames, g_device_audio_check_mono.size() - captured);
        const std::size_t stereo_samples = frames * 2;
        const esp_err_t err = static_cast<esp_err_t>(esp_codec_dev_read(
            g_audio.input_dev,
            g_device_audio_check_stereo.data(),
            static_cast<int>(stereo_samples * sizeof(int16_t))));
        if (err != ESP_OK) {
            ESP_LOGE(kLogTag,
                     "DEVICE_AUDIO status=failed stage=capture-read err=%s",
                     esp_err_to_name(err));
            ok = false;
            break;
        }

        for (std::size_t frame = 0; frame < frames; ++frame) {
            // The signed-off input path exposes two channels. Keep channel zero
            // as the mono voice lane; no new codec/I2S owner is introduced here.
            g_device_audio_check_mono[captured + frame] =
                g_device_audio_check_stereo[frame * 2];
        }
        captured += frames;
    }

    if (!close_input()) ok = false;
    return ok && captured == g_device_audio_check_mono.size();
}

bool device_audio_play_check_sample()
{
    if (!g_audio.ready || g_audio.output_dev == nullptr) return false;
    if (!open_output()) return false;

    bool ok = true;
    const esp_err_t unmute_err = static_cast<esp_err_t>(
        esp_codec_dev_set_out_mute(g_audio.output_dev, false));
    if (unmute_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "DEVICE_AUDIO status=failed stage=unmute err=%s",
                 esp_err_to_name(unmute_err));
        ok = false;
    }

    if (ok) {
        const esp_err_t write_err = static_cast<esp_err_t>(esp_codec_dev_write(
            g_audio.output_dev,
            g_device_audio_check_mono.data(),
            static_cast<int>(g_device_audio_check_mono.size() * sizeof(int16_t))));
        if (write_err != ESP_OK) {
            ESP_LOGE(kLogTag,
                     "DEVICE_AUDIO status=failed stage=playback-write err=%s",
                     esp_err_to_name(write_err));
            ok = false;
        }
    }

    if (ok) {
        const esp_err_t silence_err = static_cast<esp_err_t>(esp_codec_dev_write(
            g_audio.output_dev,
            g_silence.data(),
            static_cast<int>(g_silence.size() * sizeof(int16_t))));
        if (silence_err != ESP_OK) {
            ESP_LOGW(kLogTag,
                     "DEVICE_AUDIO silence-write err=%s",
                     esp_err_to_name(silence_err));
        }
    }

    if (!close_output()) ok = false;
    return ok;
}

bool device_audio_run_ownership_check()
{
    if (!g_audio.ready) {
        ESP_LOGE(kLogTag, "DEVICE_AUDIO status=failed stage=transport-not-ready");
        return false;
    }

    // Runtime body motion must remain mechanically idle while codec ownership
    // changes. The audio check never writes the servo transport.
    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "DEVICE_AUDIO status=failed stage=torque-precondition");
        return false;
    }

    presence_interaction_begin();
    presentation_set_state(PresentationState::Listening, "device-audio-check");
    vTaskDelay(pdMS_TO_TICKS(kDeviceAudioCueMs));

    ESP_LOGI(kLogTag,
             "DEVICE_AUDIO phase=capture frames=%u sample_rate=%d",
             static_cast<unsigned>(g_device_audio_check_mono.size()),
             kade_body_contract::kAudioSampleRateHz);
    const bool captured = device_audio_capture_check_sample();
    if (!captured) {
        presentation_set_state(PresentationState::Idle, "device-audio-check-failed");
        presence_interaction_end();
        p9_release_torque();
        return false;
    }

    presentation_set_state(PresentationState::Speaking, "device-audio-check");
    ESP_LOGI(kLogTag,
             "DEVICE_AUDIO phase=playback frames=%u",
             static_cast<unsigned>(g_device_audio_check_mono.size()));
    const bool played = device_audio_play_check_sample();

    const bool torque_released = p9_release_torque() && p10_verify_torque_released();
    presentation_set_state(PresentationState::Idle,
                           played && torque_released
                               ? "device-audio-check-complete"
                               : "device-audio-check-failed");
    presence_interaction_end();

    if (!played || !torque_released) {
        ESP_LOGE(kLogTag,
                 "DEVICE_AUDIO status=failed stage=%s",
                 played ? "torque-postcondition" : "playback");
        return false;
    }

    ESP_LOGI(kLogTag,
             "DEVICE_AUDIO status=complete capture=1 playback=1 handoff=1 torque=released");
    return true;
}

bool device_audio_make_ack(const char* request_id,
                           bool ok,
                           char* output,
                           size_t output_size)
{
    if (request_id == nullptr || request_id[0] == '\0' ||
        output == nullptr || output_size == 0) {
        return false;
    }

    cJSON* root = cJSON_CreateObject();
    cJSON* payload = cJSON_CreateObject();
    if (root == nullptr || payload == nullptr) {
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    bool built = true;
    built = built && cJSON_AddNumberToObject(root, "v", 1) != nullptr;
    built = built && cJSON_AddStringToObject(root, "id", request_id) != nullptr;
    built = built && cJSON_AddStringToObject(root, "ts", "device") != nullptr;
    built = built && cJSON_AddStringToObject(root, "kind", "ack") != nullptr;
    built = built && cJSON_AddStringToObject(root, "name", "voice.audio-check") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", ok) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "capture", ok) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "playback", ok) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "handoff", ok) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "torque_released", ok) != nullptr;
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

DeviceAudioCommandResult device_audio_execute_command(const char* raw,
                                                      char* ack,
                                                      size_t ack_size)
{
    if (raw == nullptr) return DeviceAudioCommandResult::NotDeviceAudio;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return DeviceAudioCommandResult::NotDeviceAudio;
    }

    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name) || name->valuestring == nullptr ||
        std::strcmp(name->valuestring, "voice.audio-check") != 0) {
        cJSON_Delete(root);
        return DeviceAudioCommandResult::NotDeviceAudio;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const bool valid = cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
                       cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
                       request_id->valuestring[0] != '\0' &&
                       cJSON_IsString(kind) && kind->valuestring != nullptr &&
                       std::strcmp(kind->valuestring, "command") == 0 &&
                       cJSON_IsObject(payload);
    if (!valid || std::strlen(request_id->valuestring) >= 48) {
        cJSON_Delete(root);
        return DeviceAudioCommandResult::Rejected;
    }

    char request_copy[48]{};
    std::snprintf(request_copy, sizeof(request_copy), "%s", request_id->valuestring);
    cJSON_Delete(root);

    const bool ok = device_audio_run_ownership_check();
    if (!device_audio_make_ack(request_copy, ok, ack, ack_size)) {
        return DeviceAudioCommandResult::Rejected;
    }
    return DeviceAudioCommandResult::Accepted;
}

}  // namespace
