#define probe8_draw_frame probe8_draw_frame_unsafe
#define run_probe8 run_probe8_original
#define app_main app_main_original
#include "probe8.cpp"
#undef app_main
#undef run_probe8
#undef probe8_draw_frame

#include "freertos/semphr.h"

namespace {

constexpr int kProbe8RenderRows = 16;
constexpr TickType_t kProbe8RenderTimeout = pdMS_TO_TICKS(500);

SemaphoreHandle_t g_probe8_render_done = nullptr;
std::array<uint16_t,
           kade_body_contract::kDisplayWidth * kProbe8RenderRows>
    g_probe8_render_chunk{};

bool probe8_render_done_cb(esp_lcd_panel_io_handle_t,
                           esp_lcd_panel_io_event_data_t*,
                           void*)
{
    if (g_probe8_render_done == nullptr) return false;

    BaseType_t higher_priority_task_woken = pdFALSE;
    xSemaphoreGiveFromISR(g_probe8_render_done, &higher_priority_task_woken);
    return higher_priority_task_woken == pdTRUE;
}

bool probe8_install_render_sync()
{
    g_probe8_render_done = xSemaphoreCreateBinary();
    if (g_probe8_render_done == nullptr) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=render-sync-semaphore");
        return false;
    }

    esp_lcd_panel_io_callbacks_t callbacks{};
    callbacks.on_color_trans_done = probe8_render_done_cb;
    const esp_err_t err = esp_lcd_panel_io_register_event_callbacks(
        g_probe8_surface.panel_io,
        &callbacks,
        nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE8 status=failed stage=render-sync-callback err=%s",
                 esp_err_to_name(err));
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE8 render-sync status=ready");
    return true;
}

uint16_t probe8_colour_for_row(int y, bool completed)
{
    constexpr uint16_t kDark = 0x0841;
    constexpr uint16_t kLight = 0xC618;
    constexpr uint16_t kAccent = 0x7BEF;

    if (y >= 24 && y < 28) return kLight;
    if (y >= 212 && y < 216) return kLight;
    if (completed && y >= 112 && y < 128) return kAccent;
    return kDark;
}

bool probe8_draw_frame_sync(bool completed)
{
    if (!g_probe8_surface.panel_ready ||
        g_probe8_surface.panel == nullptr ||
        g_probe8_render_done == nullptr) {
        return false;
    }

    for (int y0 = 0;
         y0 < kade_body_contract::kDisplayHeight;
         y0 += kProbe8RenderRows) {
        const int y1 = std::min(
            y0 + kProbe8RenderRows,
            kade_body_contract::kDisplayHeight);
        const int rows = y1 - y0;

        for (int local_y = 0; local_y < rows; ++local_y) {
            const uint16_t fill = probe8_colour_for_row(y0 + local_y, completed);
            auto begin = g_probe8_render_chunk.begin() +
                         (local_y * kade_body_contract::kDisplayWidth);
            auto end = begin + kade_body_contract::kDisplayWidth;
            std::fill(begin, end, fill);
        }

        while (xSemaphoreTake(g_probe8_render_done, 0) == pdTRUE) {
        }

        const esp_err_t draw_err = esp_lcd_panel_draw_bitmap(
            g_probe8_surface.panel,
            0,
            y0,
            kade_body_contract::kDisplayWidth,
            y1,
            g_probe8_render_chunk.data());
        if (draw_err != ESP_OK) {
            ESP_LOGE(kLogTag,
                     "PROBE8 status=failed stage=render-submit y=%d err=%s",
                     y0,
                     esp_err_to_name(draw_err));
            return false;
        }

        if (xSemaphoreTake(g_probe8_render_done, kProbe8RenderTimeout) != pdTRUE) {
            ESP_LOGE(kLogTag,
                     "PROBE8 status=failed stage=render-timeout y=%d",
                     y0);
            return false;
        }
    }

    if (!probe8_set_backlight(55)) return false;
    return true;
}

bool run_probe8_sync()
{
    ESP_LOGI(kLogTag, "PROBE8 phase=control");
    initialise_control_bus();

    ESP_LOGI(kLogTag, "PROBE8 phase=surface");
    if (!probe8_initialise_panel()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=surface-init");
        return false;
    }
    if (!probe8_install_render_sync()) return false;
    if (!probe8_draw_frame_sync(false)) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=surface-frame-a");
        return false;
    }
    if (!probe8_initialise_touch()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=checkpoint-init");
        return false;
    }
    if (!probe8_touch_health("health-a")) return false;

    ESP_LOGI(kLogTag, "PROBE8 phase=coexistence");
    if (!probe8_run_duplex_sequence()) return false;

    if (!probe8_touch_health("health-b")) return false;
    if (!probe8_draw_frame_sync(true)) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=surface-frame-b");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE8 status=complete sequence=coordinated one_shot=1 render_sync=1");
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

    const bool passed = run_probe8_sync();

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
