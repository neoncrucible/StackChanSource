#define app_main app_main_probe11_original
#include "probe11.cpp"
#undef app_main

#include <cstdio>
#include <cstring>

namespace {

constexpr size_t kP12FrameBytes = 384;

struct P12Ack {
    char request_id[48]{};
    char name[32]{};
    bool ok = false;
};

bool p12_extract_request_id(const char* raw, char* output, size_t output_size)
{
    if (raw == nullptr || output == nullptr || output_size == 0) return false;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const bool valid = cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
                       cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
                       request_id->valuestring[0] != '\0' &&
                       std::strlen(request_id->valuestring) < output_size;
    if (valid) {
        std::snprintf(output, output_size, "%s", request_id->valuestring);
    }
    cJSON_Delete(root);
    return valid;
}

bool p12_make_ack(const char* request_id, char* output, size_t output_size)
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

    bool ok = true;
    ok = ok && cJSON_AddNumberToObject(root, "v", 1) != nullptr;
    ok = ok && cJSON_AddStringToObject(root, "id", request_id) != nullptr;
    ok = ok && cJSON_AddStringToObject(root, "ts", "device") != nullptr;
    ok = ok && cJSON_AddStringToObject(root, "kind", "ack") != nullptr;
    ok = ok && cJSON_AddStringToObject(root, "name", "body.pose") != nullptr;
    ok = ok && cJSON_AddBoolToObject(payload, "ok", true) != nullptr;
    if (ok) {
        cJSON_AddItemToObject(root, "payload", payload);
        payload = nullptr;
    }

    char* rendered = ok ? cJSON_PrintUnformatted(root) : nullptr;
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

bool p12_decode_ack(const char* raw, P12Ack* output)
{
    if (raw == nullptr || output == nullptr) return false;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* ok = payload != nullptr
        ? cJSON_GetObjectItemCaseSensitive(payload, "ok")
        : nullptr;

    const bool valid =
        cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
        cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
        request_id->valuestring[0] != '\0' &&
        std::strlen(request_id->valuestring) < sizeof(output->request_id) &&
        cJSON_IsString(kind) && kind->valuestring != nullptr &&
        std::strcmp(kind->valuestring, "ack") == 0 &&
        cJSON_IsString(name) && name->valuestring != nullptr &&
        std::strcmp(name->valuestring, "body.pose") == 0 &&
        cJSON_IsObject(payload) && cJSON_IsBool(ok);

    if (!valid) {
        cJSON_Delete(root);
        return false;
    }

    std::snprintf(output->request_id, sizeof(output->request_id), "%s", request_id->valuestring);
    std::snprintf(output->name, sizeof(output->name), "%s", name->valuestring);
    output->ok = cJSON_IsTrue(ok);
    cJSON_Delete(root);
    return true;
}

bool p12_protocol_round_trip()
{
    constexpr const char* command =
        "{\"v\":1,\"id\":\"cp12-correlation\",\"ts\":\"host\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":0,\"pitch\":400}}";

    P11Pose pose{};
    if (!p11_decode_pose(command, &pose)) return false;

    char request_id[48]{};
    if (!p12_extract_request_id(command, request_id, sizeof(request_id))) return false;

    char ack_frame[kP12FrameBytes]{};
    if (!p12_make_ack(request_id, ack_frame, sizeof(ack_frame))) return false;

    P12Ack ack{};
    if (!p12_decode_ack(ack_frame, &ack)) return false;
    if (std::strcmp(ack.request_id, request_id) != 0 ||
        std::strcmp(ack.name, "body.pose") != 0 || !ack.ok) {
        return false;
    }

    P12Ack rejected{};
    if (p12_decode_ack(
            "{\"v\":1,\"id\":\"x\",\"kind\":\"event\",\"name\":\"body.pose\",\"payload\":{\"ok\":true}}",
            &rejected)) {
        return false;
    }
    if (p12_extract_request_id(
            "{\"v\":1,\"id\":\"\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{}}",
            request_id,
            sizeof(request_id))) {
        return false;
    }

    return true;
}

bool run_probe12()
{
    ESP_LOGI(kLogTag, "PROBE12 phase=baseline");
    if (!run_probe11()) {
        ESP_LOGE(kLogTag, "PROBE12 status=failed stage=baseline");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE12 phase=correlation");
    if (!p12_protocol_round_trip()) {
        ESP_LOGE(kLogTag, "PROBE12 status=failed stage=correlation");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "PROBE12 status=failed stage=final-release");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE12 status=complete correlated=1 ack_roundtrip=1 reject_malformed=1 torque=released one_shot=1");
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

    const bool ok = run_probe12();
    uint32_t heartbeat_seq = 0;
    const int64_t heartbeat_epoch_us = esp_timer_get_time();
    while (true) {
        const int64_t uptime_ms = (esp_timer_get_time() - heartbeat_epoch_us) / 1000;
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%u uptime_ms=%lld free_heap=%u status=%s",
                 static_cast<unsigned>(heartbeat_seq++),
                 static_cast<long long>(uptime_ms),
                 static_cast<unsigned>(esp_get_free_heap_size()),
                 ok ? "ok" : "failed");
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
