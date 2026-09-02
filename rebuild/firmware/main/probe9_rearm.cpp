#define KADE_PROBE8_NO_APP_MAIN 1
#include "probe8_sync.cpp"
#undef KADE_PROBE8_NO_APP_MAIN

#define app_main app_main_probe9_original
#include "probe9.cpp"
#undef app_main

namespace {

bool p9_prepare_verify_transition()
{
    if (g_audio.tx == nullptr || g_audio.rx == nullptr) {
        ESP_LOGE(kLogTag, "PROBE9 verify-transition status=failed stage=missing-channel");
        return false;
    }

    const esp_err_t tx_err = i2s_channel_enable(g_audio.tx);
    if (tx_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE9 verify-transition status=failed stage=tx-rearm err=%s",
                 esp_err_to_name(tx_err));
        return false;
    }

    const esp_err_t rx_err = i2s_channel_enable(g_audio.rx);
    if (rx_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE9 verify-transition status=failed stage=rx-rearm err=%s",
                 esp_err_to_name(rx_err));
        i2s_channel_disable(g_audio.tx);
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE9 verify-transition status=ready");
    return true;
}

bool p9_run_integrated_gate_rearm()
{
    ESP_LOGI(kLogTag, "PROBE9 phase=baseline");
    if (!run_probe8()) {
        ESP_LOGE(kLogTag, "PROBE9 status=failed stage=baseline");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE9 phase=integration");
    if (!p9_initialise_power_control()) {
        p9_fail_closed("control-init");
        return false;
    }
    if (!p9_set_power(true)) {
        p9_fail_closed("control-enable");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP9WarmSettleMs));

    if (!p9_initialise_uart()) {
        p9_fail_closed("transport-init");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP9TransportSettleMs));

    if (!p9_warm_transport()) {
        p9_fail_closed("transport-warmup");
        return false;
    }
    if (!p9_release_torque()) {
        p9_fail_closed("preflight-release");
        return false;
    }

    int zero_position = 0;
    if (!p9_load_zero_read_only(&zero_position)) {
        p9_fail_closed("read-only-state");
        return false;
    }

    int start_raw = 0;
    if (!p9_read_position(kP9PrimaryId, &start_raw)) {
        p9_fail_closed("position-read");
        return false;
    }
    const int start_angle = p9_raw_to_angle(start_raw, zero_position);
    if (start_angle < kade_body_contract::kSafeYawMinTenths ||
        start_angle > kade_body_contract::kSafeYawMaxTenths) {
        p9_fail_closed("position-envelope");
        return false;
    }

    int target_angle = 0;
    int target_raw = 0;
    if (!p9_choose_target(start_angle, &target_angle) ||
        !p9_angle_to_raw(target_angle, zero_position, &target_raw)) {
        p9_fail_closed("target-envelope");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE9 status=ready preserve_zero=1 release_torque=1 start=%d target=%d",
             start_angle,
             target_angle);
    vTaskDelay(pdMS_TO_TICKS(500));

    if (!p9_enable_primary_torque()) {
        p9_fail_closed("execute-enable");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE9 phase=execute-a");
    if (!p9_ramp(start_angle, target_angle, zero_position)) {
        p9_fail_closed("execute-a-command");
        return false;
    }

    int reached_angle = 0;
    if (!p9_wait_settled(
            target_angle, zero_position, kP9MoveTimeoutMs, &reached_angle)) {
        p9_fail_closed("execute-a-settle");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP9HoldMs));

    ESP_LOGI(kLogTag, "PROBE9 phase=execute-b");
    if (!p9_ramp(target_angle, start_angle, zero_position)) {
        p9_fail_closed("execute-b-command");
        return false;
    }

    int final_angle = 0;
    if (!p9_wait_settled(
            start_angle, zero_position, kP9ReturnTimeoutMs, &final_angle)) {
        p9_fail_closed("execute-b-settle");
        return false;
    }
    if (!p9_release_torque()) {
        p9_fail_closed("final-release");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE9 phase=verify");
    if (!probe8_touch_health("health-c")) {
        p9_fail_closed("verify-health");
        return false;
    }
    if (!p9_prepare_verify_transition()) {
        p9_fail_closed("verify-transition");
        return false;
    }
    if (!open_input()) {
        p9_fail_closed("verify-open");
        return false;
    }
    if (!sample_input("post")) {
        close_input();
        p9_fail_closed("verify-sample");
        return false;
    }
    if (!close_input()) {
        p9_fail_closed("verify-close");
        return false;
    }
    if (!probe8_draw_frame(true)) {
        p9_fail_closed("verify-surface");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE9 status=complete first_error=%d return_error=%d torque=released preserve_zero=1 one_shot=1 transition=rearmed",
             p9_abs(reached_angle - target_angle),
             p9_abs(final_angle - start_angle));
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
    probe8_log_contract();

    const bool passed = p9_run_integrated_gate_rearm();

    uint32_t heartbeat_seq = 0;
    const int64_t start_us = esp_timer_get_time();
    while (true) {
        const uint32_t uptime_ms = static_cast<uint32_t>(
            (esp_timer_get_time() - start_us) / 1000);
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu32
                 " free_heap=%" PRIu32 " status=%s",
                 heartbeat_seq++,
                 uptime_ms,
                 static_cast<uint32_t>(esp_get_free_heap_size()),
                 passed ? "ok" : "failed");
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
