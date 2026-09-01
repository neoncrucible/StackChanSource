#define run_probe run_probe_original
#define app_main app_main_original
#include "probe6.cpp"
#undef app_main
#undef run_probe

namespace {

constexpr int kWarmSettleMs = 650;
constexpr int kWarmTransportSettleMs = 100;
constexpr int kWarmRetryDelayMs = 70;
constexpr int kWarmAttempts = 3;

bool read_secondary_raw_position(int* raw_position)
{
    if (raw_position == nullptr) return false;
    uint8_t data[2]{};
    if (!read_register(kSecondaryId, kRegPresentPosition, data, sizeof(data))) return false;
    *raw_position = (static_cast<int>(data[0]) << 8) | data[1];
    return *raw_position >= kRawPositionMin && *raw_position <= kRawPositionMax;
}

bool warm_transport()
{
    for (int attempt = 1; attempt <= kWarmAttempts; ++attempt) {
        int primary_raw = -1;
        int secondary_raw = -1;
        const bool primary_ok = read_raw_position(&primary_raw);
        const bool secondary_ok = read_secondary_raw_position(&secondary_raw);

        ESP_LOGI(kLogTag,
                 "PROBE6 warm attempt=%d primary_ok=%d secondary_ok=%d",
                 attempt,
                 primary_ok ? 1 : 0,
                 secondary_ok ? 1 : 0);

        if (primary_ok && secondary_ok) return true;
        if (attempt < kWarmAttempts) vTaskDelay(pdMS_TO_TICKS(kWarmRetryDelayMs));
    }
    return false;
}

bool run_probe_warm()
{
    ESP_LOGI(kLogTag, "PROBE6 phase=control-bus");
    if (!initialise_power_control()) return false;

    if (!set_power_enabled(true)) {
        fail_closed("control-enable");
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(kWarmSettleMs));

    if (!initialise_uart()) {
        fail_closed("transport-init");
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(kWarmTransportSettleMs));

    if (!warm_transport()) {
        fail_closed("transport-warmup");
        return false;
    }

    if (!release_torque()) {
        fail_closed("preflight-release");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE6 phase=read-only-state");
    int zero_position = 0;
    if (!load_zero_position_read_only(&zero_position)) {
        fail_closed("read-only-state");
        return false;
    }

    int start_raw = 0;
    if (!read_raw_position(&start_raw)) {
        fail_closed("position-read");
        return false;
    }
    const int start_angle = raw_to_angle_tenths(start_raw, zero_position);
    if (start_angle < kade_body_contract::kSafeYawMinTenths ||
        start_angle > kade_body_contract::kSafeYawMaxTenths) {
        fail_closed("position-envelope");
        return false;
    }

    int target_angle = 0;
    int target_raw = 0;
    if (!choose_target(start_angle, &target_angle) ||
        !angle_to_raw(target_angle, zero_position, &target_raw)) {
        fail_closed("target-envelope");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE6 status=ready preserve_zero=1 release_torque=1 start=%d target=%d",
             start_angle,
             target_angle);
    vTaskDelay(pdMS_TO_TICKS(1000));

    if (!enable_primary_torque()) {
        fail_closed("execute-enable");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE6 phase=execute-a");
    if (!ramp_to_angle(start_angle, target_angle, zero_position)) {
        fail_closed("execute-a-command");
        return false;
    }

    int reached_angle = 0;
    if (!wait_until_settled(target_angle, zero_position, kMoveTimeoutMs, &reached_angle)) {
        fail_closed("execute-a-settle");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kHoldMs));

    ESP_LOGI(kLogTag, "PROBE6 phase=execute-b");
    if (!ramp_to_angle(target_angle, start_angle, zero_position)) {
        fail_closed("execute-b-command");
        return false;
    }

    int final_angle = 0;
    if (!wait_until_settled(start_angle, zero_position, kReturnTimeoutMs, &final_angle)) {
        fail_closed("execute-b-settle");
        return false;
    }

    if (!release_torque()) {
        fail_closed("final-release");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE6 status=complete first_error=%d return_error=%d torque=released preserve_zero=1",
             abs_int(reached_angle - target_angle),
             abs_int(final_angle - start_angle));
    return true;
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));

    const esp_app_desc_t* app = esp_app_get_description();
    ESP_LOGI(kLogTag,
             "BODY_BOOT firmware=%s device_id=%s reset=%s",
             app != nullptr ? app->version : "unknown",
             device_id,
             reset_reason_name(esp_reset_reason()));
    log_contract();

    const bool passed = run_probe_warm();
    if (!passed && !g_runtime.failed) fail_closed("unknown");

    uint32_t heartbeat_seq = 0;
    const int64_t start_us = esp_timer_get_time();
    while (true) {
        const uint32_t uptime_ms = static_cast<uint32_t>((esp_timer_get_time() - start_us) / 1000);
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu32 " free_heap=%" PRIu32 " status=%s",
                 heartbeat_seq++,
                 uptime_ms,
                 static_cast<uint32_t>(esp_get_free_heap_size()),
                 passed ? "ok" : "failed");
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
