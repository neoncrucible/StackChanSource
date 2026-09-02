#include "esp_err.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static esp_err_t probe8_sync_draw_bitmap(esp_lcd_panel_handle_t panel,
                                         int x_start,
                                         int y_start,
                                         int x_end,
                                         int y_end,
                                         const void* color_data);

// Keep Checkpoint 8's already-proven logic and inject synchronization only at
// the LCD colour-transfer boundary. This avoids duplicating or wrapping its
// app_main/run lifecycle while still enforcing the ESP-LCD buffer lifetime
// contract for every diagnostic frame transfer.
#define esp_lcd_panel_draw_bitmap probe8_sync_draw_bitmap
#include "probe8.cpp"
#undef esp_lcd_panel_draw_bitmap

namespace {

constexpr TickType_t kProbe8RenderTimeout = pdMS_TO_TICKS(500);
SemaphoreHandle_t g_probe8_render_done = nullptr;
bool g_probe8_render_sync_ready = false;

bool probe8_render_done_cb(esp_lcd_panel_io_handle_t,
                           esp_lcd_panel_io_event_data_t*,
                           void*)
{
    if (g_probe8_render_done == nullptr) return false;

    BaseType_t higher_priority_task_woken = pdFALSE;
    xSemaphoreGiveFromISR(g_probe8_render_done, &higher_priority_task_woken);
    return higher_priority_task_woken == pdTRUE;
}

esp_err_t probe8_ensure_render_sync()
{
    if (g_probe8_render_sync_ready) return ESP_OK;
    if (g_probe8_surface.panel_io == nullptr) return ESP_ERR_INVALID_STATE;

    g_probe8_render_done = xSemaphoreCreateBinary();
    if (g_probe8_render_done == nullptr) return ESP_ERR_NO_MEM;

    esp_lcd_panel_io_callbacks_t callbacks{};
    callbacks.on_color_trans_done = probe8_render_done_cb;
    const esp_err_t err = esp_lcd_panel_io_register_event_callbacks(
        g_probe8_surface.panel_io,
        &callbacks,
        nullptr);
    if (err != ESP_OK) {
        vSemaphoreDelete(g_probe8_render_done);
        g_probe8_render_done = nullptr;
        return err;
    }

    g_probe8_render_sync_ready = true;
    ESP_LOGI(kLogTag, "PROBE8 render-sync status=ready");
    return ESP_OK;
}

}  // namespace

static esp_err_t probe8_sync_draw_bitmap(esp_lcd_panel_handle_t panel,
                                         int x_start,
                                         int y_start,
                                         int x_end,
                                         int y_end,
                                         const void* color_data)
{
    const esp_err_t sync_err = probe8_ensure_render_sync();
    if (sync_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE8 render-sync status=failed err=%s",
                 esp_err_to_name(sync_err));
        return sync_err;
    }

    while (xSemaphoreTake(g_probe8_render_done, 0) == pdTRUE) {
    }

    const esp_err_t submit_err = esp_lcd_panel_draw_bitmap(
        panel,
        x_start,
        y_start,
        x_end,
        y_end,
        color_data);
    if (submit_err != ESP_OK) return submit_err;

    if (xSemaphoreTake(g_probe8_render_done, kProbe8RenderTimeout) != pdTRUE) {
        ESP_LOGE(kLogTag,
                 "PROBE8 render-sync status=failed stage=transfer-timeout y=%d",
                 y_start);
        return ESP_ERR_TIMEOUT;
    }

    return ESP_OK;
}
