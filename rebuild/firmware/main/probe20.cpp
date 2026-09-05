#define app_main app_main_probe16_original
#include "probe16.cpp"
#undef app_main

#include <utility>

#include "presentation.cpp"
#include "presence_engine.cpp"
#include "device_audio.cpp"

#include <cstdio>
#include <cstring>

#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"

namespace {

constexpr size_t kP20LineBytes = kP16FrameBytes;

enum class P20PresentationResult : uint8_t {
    NotPresentation = 0,
    Accepted,
    Rejected,
};

bool p20_presentation_state_from_name(const char* name, PresentationState* state)
{
    if (name == nullptr || state == nullptr) return false;
    if (std::strcmp(name, "idle") == 0) *state = PresentationState::Idle;
    else if (std::strcmp(name, "attentive") == 0) *state = PresentationState::Attentive;
    else if (std::strcmp(name, "listening") == 0) *state = PresentationState::Listening;
    else if (std::strcmp(name, "thinking") == 0) *state = PresentationState::Thinking;
    else if (std::strcmp(name, "speaking") == 0) *state = PresentationState::Speaking;
    else if (std::strcmp(name, "tool-working") == 0) *state = PresentationState::ToolWorking;
    else if (std::strcmp(name, "offline") == 0) *state = PresentationState::Offline;
    else if (std::strcmp(name, "degraded") == 0) *state = PresentationState::Degraded;
    else if (std::strcmp(name, "fault") == 0) *state = PresentationState::Fault;
    else if (std::strcmp(name, "recovery") == 0) *state = PresentationState::Recovery;
    else return false;
    return true;
}

bool p20_make_presentation_ack(const char* request_id,
                               const char* state,
                               char* output,
                               size_t output_size)
{
    if (request_id == nullptr || request_id[0] == '\0' ||
        state == nullptr || state[0] == '\0' || output == nullptr || output_size == 0) {
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
    built = built && cJSON_AddStringToObject(root, "name", "presentation.state") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", true) != nullptr;
    built = built && cJSON_AddStringToObject(payload, "state", state) != nullptr;
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

P20PresentationResult p20_execute_presentation_command(const char* raw,
                                                       char* ack,
                                                       size_t ack_size)
{
    if (raw == nullptr) return P20PresentationResult::NotPresentation;
    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return P20PresentationResult::NotPresentation;
    }

    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name) || name->valuestring == nullptr ||
        std::strcmp(name->valuestring, "presentation.state") != 0) {
        cJSON_Delete(root);
        return P20PresentationResult::NotPresentation;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* state_item = payload ? cJSON_GetObjectItemCaseSensitive(payload, "state") : nullptr;

    PresentationState target{};
    const bool valid = cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
                       cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
                       request_id->valuestring[0] != '\0' &&
                       cJSON_IsString(kind) && kind->valuestring != nullptr &&
                       std::strcmp(kind->valuestring, "command") == 0 &&
                       cJSON_IsObject(payload) &&
                       cJSON_IsString(state_item) && state_item->valuestring != nullptr &&
                       p20_presentation_state_from_name(state_item->valuestring, &target);
    if (!valid) {
        cJSON_Delete(root);
        return P20PresentationResult::Rejected;
    }

    char request_copy[48]{};
    char state_copy[24]{};
    if (std::strlen(request_id->valuestring) >= sizeof(request_copy) ||
        std::strlen(state_item->valuestring) >= sizeof(state_copy)) {
        cJSON_Delete(root);
        return P20PresentationResult::Rejected;
    }
    std::snprintf(request_copy, sizeof(request_copy), "%s", request_id->valuestring);
    std::snprintf(state_copy, sizeof(state_copy), "%s", state_item->valuestring);
    cJSON_Delete(root);

    if (target == PresentationState::Idle) {
        presentation_set_state(target, "host-state");
        presence_interaction_end();
    } else {
        presence_interaction_begin();
        presentation_set_state(target, "host-state");
    }

    if (!p20_make_presentation_ack(request_copy, state_copy, ack, ack_size)) {
        return P20PresentationResult::Rejected;
    }
    return P20PresentationResult::Accepted;
}

void p20_protocol_task(void*)
{
    char line[kP20LineBytes]{};
    while (true) {
        if (std::fgets(line, sizeof(line), stdin) == nullptr) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        size_t len = std::strlen(line);
        while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
            line[--len] = '\0';
        }
        if (len == 0) continue;

        ESP_LOGI(kLogTag, "PROBE20 phase=rx bytes=%u", static_cast<unsigned>(len));

        char ack[kP16FrameBytes]{};
        const DeviceAudioCommandResult audio_result =
            device_audio_execute_command(line, ack, sizeof(ack));
        if (audio_result == DeviceAudioCommandResult::Accepted) {
            std::printf("%s\n", ack);
            std::fflush(stdout);
            ESP_LOGI(kLogTag, "PROBE20 device-audio=ack-sent correlated=1");
            continue;
        }
        if (audio_result == DeviceAudioCommandResult::Rejected) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "device-audio-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "PROBE20 device-audio=rejected torque=released");
            continue;
        }

        const P20PresentationResult presentation_result =
            p20_execute_presentation_command(line, ack, sizeof(ack));
        if (presentation_result == P20PresentationResult::Accepted) {
            std::printf("%s\n", ack);
            std::fflush(stdout);
            ESP_LOGI(kLogTag, "PROBE20 presentation=ack-sent correlated=1");
            continue;
        }
        if (presentation_result == P20PresentationResult::Rejected) {
            ESP_LOGE(kLogTag, "PROBE20 presentation=rejected");
            continue;
        }

        presence_interaction_begin();
        presentation_set_state(PresentationState::Attentive, "body-command");

        if (!p16_execute_pose_command(line, ack, sizeof(ack))) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "body-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "PROBE20 status=rejected torque=released");
            continue;
        }

        std::printf("%s\n", ack);
        std::fflush(stdout);
        presentation_set_state(PresentationState::Idle, "body-complete");
        presence_interaction_end();
        ESP_LOGI(kLogTag, "PROBE20 status=ack-sent executed=1 torque=released");
    }
}

bool run_probe20()
{
    ESP_LOGI(kLogTag, "PROBE20 phase=baseline");
    if (!run_probe16()) {
        ESP_LOGE(kLogTag, "PROBE20 status=failed stage=baseline");
        return false;
    }

    if (!g_audio.ready || g_audio.input_dev == nullptr || g_audio.output_dev == nullptr) {
        ESP_LOGE(kLogTag, "PROBE20 status=failed stage=audio-transport");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "PROBE20 status=failed stage=pre-transport-release");
        return false;
    }

    usb_serial_jtag_driver_config_t usb_cfg = {
        .tx_buffer_size = 1024,
        .rx_buffer_size = 1024,
    };
    const esp_err_t usb_err = usb_serial_jtag_driver_install(&usb_cfg);
    if (usb_err != ESP_OK && usb_err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(kLogTag,
                 "PROBE20 status=failed stage=usb-driver-install err=%s",
                 esp_err_to_name(usb_err));
        return false;
    }
    usb_serial_jtag_vfs_use_driver();

    const BaseType_t created = xTaskCreate(
        p20_protocol_task,
        "kade-p20-rx",
        4096,
        nullptr,
        5,
        nullptr);
    if (created != pdPASS) {
        ESP_LOGE(kLogTag, "PROBE20 status=failed stage=rx-task");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE20 status=ready control=usb-serial-jtag audio=runtime-duplex handoff=1 torque=released");
    return true;
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));
    const esp_app_desc_t* app = esp_app_get_description();
    ESP_LOGI(kLogTag,
             "BODY_BOOT device=%s fw=%s idf=%s reset=%d heap=%u",
             device_id,
             app != nullptr ? app->version : "unknown",
             esp_get_idf_version(),
             static_cast<int>(esp_reset_reason()),
             static_cast<unsigned>(esp_get_free_heap_size()));

    const bool ok = run_probe20();
    const bool presentation_ok = presentation_start(ok);
    if (!presentation_ok) {
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=start");
    }

    const bool presence_ok = presentation_ok && presence_start();
    if (!presence_ok) {
        ESP_LOGE(kLogTag, "PRESENCE status=failed stage=start");
    }

    uint32_t heartbeat_seq = 0;
    const int64_t heartbeat_epoch_us = esp_timer_get_time();
    while (true) {
        const int64_t uptime_ms = (esp_timer_get_time() - heartbeat_epoch_us) / 1000;
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%u uptime_ms=%lld free_heap=%u status=%s presentation=%s presence=%s audio=%s",
                 static_cast<unsigned>(heartbeat_seq++),
                 static_cast<long long>(uptime_ms),
                 static_cast<unsigned>(esp_get_free_heap_size()),
                 ok ? "ok" : "failed",
                 presentation_ok ? "ready" : "failed",
                 presence_ok ? "ready" : "failed",
                 g_audio.ready ? "ready" : "failed");
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
