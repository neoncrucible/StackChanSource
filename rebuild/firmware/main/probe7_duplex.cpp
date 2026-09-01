#define run_probe7 run_probe7_original
#define app_main app_main_original
#include "probe7_stable.cpp"
#undef app_main
#undef run_probe7

namespace {

bool run_probe7_duplex()
{
    ESP_LOGI(kLogTag, "PROBE7 phase=control");
    initialise_control_bus();

    ESP_LOGI(kLogTag, "PROBE7 phase=transport");
    if (!initialise_transport()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=transport-init");
        return false;
    }

    bool input_open = false;
    bool output_open = false;

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-a");
    if (!open_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-a-open");
        return false;
    }
    input_open = true;

    if (!sample_input("stage-a")) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-a-sample");
        close_input();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(100));

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-b");
    if (!open_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-open");
        close_input();
        return false;
    }
    output_open = true;

    if (!run_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-run");
        if (output_open) close_output();
        if (input_open) close_input();
        return false;
    }

    if (!close_output()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-b-close");
        if (input_open) close_input();
        return false;
    }
    output_open = false;

    // Keep the input side open across the middle stage. This is the production-like
    // duplex lifecycle and avoids a synthetic close/reopen transition between stages.
    vTaskDelay(pdMS_TO_TICKS(150));

    ESP_LOGI(kLogTag, "PROBE7 phase=stage-c");
    if (!sample_input("stage-c")) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-c-sample");
        if (input_open) close_input();
        return false;
    }

    if (!close_input()) {
        ESP_LOGE(kLogTag, "PROBE7 status=failed stage=stage-c-close");
        return false;
    }
    input_open = false;

    ESP_LOGI(kLogTag, "PROBE7 status=complete sequence=3 transport=persistent lifecycle=duplex");
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

    const bool passed = run_probe7_duplex();

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
