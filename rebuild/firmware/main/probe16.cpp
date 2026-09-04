#ifdef app_main
#define KADE_PROBE16_EMBEDDED 1
#undef app_main
#endif

#define app_main app_main_probe11_original
#include "probe11.cpp"
#undef app_main

#include <cstdio>
#include <cstring>

namespace {

constexpr int kP16OffsetTenths = 40;
constexpr int kP16HoldMs = 200;
constexpr size_t kP16FrameBytes = 384;

bool p16_extract_request_id(const char* raw, char* output, size_t output_size)
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
    if (valid) std::snprintf(output, output_size, "%s", request_id->valuestring);
    cJSON_Delete(root);
    return valid;
}

bool p16_make_ack(const char* request_id, bool ok, char* output, size_t output_size)
{
    if (request_id == nullptr || request_id[0] == '\0' || output == nullptr || output_size == 0) {
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
    built = built && cJSON_AddStringToObject(root, "name", "body.pose") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", ok) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "executed", ok) != nullptr;
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

bool p16_execute_pose_command(const char* raw, char* ack, size_t ack_size)
{
    P11Pose target{};
    char request_id[48]{};
    if (!p11_decode_pose(raw, &target) ||
        !p16_extract_request_id(raw, request_id, sizeof(request_id))) {
        return false;
    }

    int yaw_zero_before = 0;
    int pitch_zero_before = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &yaw_zero_before) ||
        !p10_load_zero_read_only("zero_pos_2", &pitch_zero_before)) {
        return false;
    }

    int yaw_raw = 0;
    int pitch_raw = 0;
    if (!p9_read_position(kP9PrimaryId, &yaw_raw) ||
        !p9_read_position(kP9SecondaryId, &pitch_raw)) {
        return false;
    }
    const P11Pose start{
        .yaw = p9_raw_to_angle(yaw_raw, yaw_zero_before),
        .pitch = p10_raw_to_angle(pitch_raw, pitch_zero_before),
    };
    if (start.yaw < kade_body_contract::kSafeYawMinTenths ||
        start.yaw > kade_body_contract::kSafeYawMaxTenths ||
        start.pitch < kade_body_contract::kSafePitchMinTenths ||
        start.pitch > kade_body_contract::kSafePitchMaxTenths) {
        return false;
    }

    if (!p9_enable_primary_torque() || !p10_enable_active_torque()) {
        p9_release_torque();
        return false;
    }
    if (!p11_ramp_dual(start, target, yaw_zero_before, pitch_zero_before)) {
        p9_release_torque();
        return false;
    }

    P11Pose reached{};
    if (!p11_wait_dual(target, yaw_zero_before, pitch_zero_before, kP11MoveTimeoutMs, &reached)) {
        p9_release_torque();
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP16HoldMs));

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        return false;
    }

    int yaw_zero_after = 0;
    int pitch_zero_after = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &yaw_zero_after) ||
        !p10_load_zero_read_only("zero_pos_2", &pitch_zero_after) ||
        yaw_zero_before != yaw_zero_after || pitch_zero_before != pitch_zero_after) {
        return false;
    }

    return p16_make_ack(request_id, true, ack, ack_size);
}

bool p16_ack_valid(const char* raw, const char* request_id)
{
    if (raw == nullptr || request_id == nullptr) return false;
    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }
    const cJSON* id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* ok = payload ? cJSON_GetObjectItemCaseSensitive(payload, "ok") : nullptr;
    const cJSON* executed = payload ? cJSON_GetObjectItemCaseSensitive(payload, "executed") : nullptr;
    const cJSON* released = payload ? cJSON_GetObjectItemCaseSensitive(payload, "torque_released") : nullptr;
    const bool valid = cJSON_IsString(id) && id->valuestring != nullptr &&
                       std::strcmp(id->valuestring, request_id) == 0 &&
                       cJSON_IsString(kind) && std::strcmp(kind->valuestring, "ack") == 0 &&
                       cJSON_IsString(name) && std::strcmp(name->valuestring, "body.pose") == 0 &&
                       cJSON_IsTrue(ok) && cJSON_IsTrue(executed) && cJSON_IsTrue(released);
    cJSON_Delete(root);
    return valid;
}

bool run_probe16()
{
    ESP_LOGI(kLogTag, "PROBE16 phase=baseline");
    if (!run_probe11()) {
        ESP_LOGE(kLogTag, "PROBE16 status=failed stage=baseline");
        return false;
    }

    int yaw_zero = 0;
    int pitch_zero = 0;
    int yaw_raw = 0;
    int pitch_raw = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &yaw_zero) ||
        !p10_load_zero_read_only("zero_pos_2", &pitch_zero) ||
        !p9_read_position(kP9PrimaryId, &yaw_raw) ||
        !p9_read_position(kP9SecondaryId, &pitch_raw)) {
        p11_fail_closed("cp16-read-state");
        return false;
    }

    const P11Pose start{
        .yaw = p9_raw_to_angle(yaw_raw, yaw_zero),
        .pitch = p10_raw_to_angle(pitch_raw, pitch_zero),
    };
    P11Pose requested{};
    if (!p11_choose_target(start.yaw, kade_body_contract::kSafeYawMinTenths,
                           kade_body_contract::kSafeYawMaxTenths, &requested.yaw) ||
        !p11_choose_target(start.pitch, kade_body_contract::kSafePitchMinTenths,
                           kade_body_contract::kSafePitchMaxTenths, &requested.pitch)) {
        p11_fail_closed("cp16-target");
        return false;
    }

    if (requested.yaw > start.yaw) requested.yaw = start.yaw + kP16OffsetTenths;
    else requested.yaw = start.yaw - kP16OffsetTenths;
    if (requested.pitch > start.pitch) requested.pitch = start.pitch + kP16OffsetTenths;
    else requested.pitch = start.pitch - kP16OffsetTenths;

    char command[kP16FrameBytes]{};
    const int command_len = std::snprintf(
        command, sizeof(command),
        "{\"v\":1,\"id\":\"cp16-execute\",\"ts\":\"host\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":%d,\"pitch\":%d}}",
        requested.yaw, requested.pitch);
    if (command_len <= 0 || command_len >= static_cast<int>(sizeof(command))) {
        p11_fail_closed("cp16-frame");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE16 phase=execute");
    char ack[kP16FrameBytes]{};
    if (!p16_execute_pose_command(command, ack, sizeof(ack))) {
        p11_fail_closed("cp16-execute");
        return false;
    }
    if (!p16_ack_valid(ack, "cp16-execute")) {
        p11_fail_closed("cp16-ack");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        p11_fail_closed("cp16-final-release");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE16 status=complete executed=1 correlated=1 ack_after_execute=1 torque=released preserve_zero=1 one_shot=1");
    return true;
}

}  // namespace

#ifndef KADE_PROBE16_EMBEDDED
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

    const bool ok = run_probe16();
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
#endif
