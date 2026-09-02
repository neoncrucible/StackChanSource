#define run_probe7 run_probe7_original
#define app_main app_main_original
#include "probe7_stable.cpp"
#undef app_main
#undef run_probe7

#include <array>

#include "driver/spi_master.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"

namespace {

constexpr gpio_num_t kP8LcdMosi = GPIO_NUM_37;
constexpr gpio_num_t kP8LcdClock = GPIO_NUM_36;
constexpr gpio_num_t kP8LcdCs = GPIO_NUM_3;
constexpr gpio_num_t kP8LcdDc = GPIO_NUM_35;
constexpr spi_host_device_t kP8LcdHost = SPI3_HOST;
constexpr uint8_t kP8TouchAddress = 0x38;

struct Probe8Surface {
    esp_lcd_panel_io_handle_t panel_io = nullptr;
    esp_lcd_panel_handle_t panel = nullptr;
    i2c_master_dev_handle_t touch = nullptr;
    bool panel_ready = false;
    bool touch_ready = false;
};

Probe8Surface g_probe8_surface;

bool probe8_try_read(i2c_master_dev_handle_t device, uint8_t reg, uint8_t* value)
{
    if (device == nullptr || value == nullptr) return false;
    return i2c_master_transmit_receive(device, &reg, 1, value, 1, kI2cTimeoutMs) == ESP_OK;
}

bool probe8_set_backlight(uint8_t percent)
{
    if (percent > 100) percent = 100;

    uint8_t rail = 0;
    if (!probe8_try_read(g_control.pmic, 0x90, &rail)) return false;

    if (percent == 0) {
        const uint8_t payload[2] = {0x90, static_cast<uint8_t>(rail & 0x7F)};
        return i2c_master_transmit(g_control.pmic, payload, sizeof(payload), kI2cTimeoutMs) == ESP_OK;
    }

    const uint8_t register_value = static_cast<uint8_t>(20 + (static_cast<uint16_t>(percent) * 8 / 100));
    const uint8_t level_payload[2] = {0x99, register_value};
    if (i2c_master_transmit(g_control.pmic, level_payload, sizeof(level_payload), kI2cTimeoutMs) != ESP_OK) {
        return false;
    }

    const uint8_t enable_payload[2] = {0x90, static_cast<uint8_t>(rail | 0x80)};
    return i2c_master_transmit(g_control.pmic, enable_payload, sizeof(enable_payload), kI2cTimeoutMs) == ESP_OK;
}

bool probe8_reset_panel()
{
    const uint8_t reset_low[2] = {0x03, 0x81};
    if (i2c_master_transmit(g_control.io_expander, reset_low, sizeof(reset_low), kI2cTimeoutMs) != ESP_OK) {
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(20));

    const uint8_t reset_high[2] = {0x03, 0x83};
    if (i2c_master_transmit(g_control.io_expander, reset_high, sizeof(reset_high), kI2cTimeoutMs) != ESP_OK) {
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
    return true;
}

bool probe8_initialise_panel()
{
    spi_bus_config_t bus_config{};
    bus_config.mosi_io_num = kP8LcdMosi;
    bus_config.miso_io_num = GPIO_NUM_NC;
    bus_config.sclk_io_num = kP8LcdClock;
    bus_config.quadwp_io_num = GPIO_NUM_NC;
    bus_config.quadhd_io_num = GPIO_NUM_NC;
    bus_config.max_transfer_sz = kade_body_contract::kDisplayWidth *
                                 kade_body_contract::kDisplayHeight *
                                 static_cast<int>(sizeof(uint16_t));
    if (spi_bus_initialize(kP8LcdHost, &bus_config, SPI_DMA_CH_AUTO) != ESP_OK) return false;

    esp_lcd_panel_io_spi_config_t io_config{};
    io_config.cs_gpio_num = kP8LcdCs;
    io_config.dc_gpio_num = kP8LcdDc;
    io_config.spi_mode = 2;
    io_config.pclk_hz = 40 * 1000 * 1000;
    io_config.trans_queue_depth = 10;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    if (esp_lcd_new_panel_io_spi(kP8LcdHost, &io_config, &g_probe8_surface.panel_io) != ESP_OK) return false;

    esp_lcd_panel_dev_config_t panel_config{};
    panel_config.reset_gpio_num = GPIO_NUM_NC;
    panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR;
    panel_config.bits_per_pixel = 16;
    if (esp_lcd_new_panel_ili9341(g_probe8_surface.panel_io, &panel_config, &g_probe8_surface.panel) != ESP_OK) {
        return false;
    }

    if (esp_lcd_panel_reset(g_probe8_surface.panel) != ESP_OK) return false;
    if (!probe8_reset_panel()) return false;
    if (esp_lcd_panel_init(g_probe8_surface.panel) != ESP_OK) return false;
    if (esp_lcd_panel_invert_color(g_probe8_surface.panel, true) != ESP_OK) return false;
    if (esp_lcd_panel_swap_xy(g_probe8_surface.panel, false) != ESP_OK) return false;
    if (esp_lcd_panel_mirror(g_probe8_surface.panel, false, false) != ESP_OK) return false;

    const esp_err_t display_on = esp_lcd_panel_disp_on_off(g_probe8_surface.panel, true);
    if (display_on != ESP_OK && display_on != ESP_ERR_NOT_SUPPORTED) return false;

    g_probe8_surface.panel_ready = true;
    return true;
}

bool probe8_draw_frame(bool completed)
{
    if (!g_probe8_surface.panel_ready || g_probe8_surface.panel == nullptr) return false;

    constexpr uint16_t kDark = 0x0841;
    constexpr uint16_t kLight = 0xC618;
    constexpr uint16_t kAccent = 0x7BEF;
    std::array<uint16_t, kade_body_contract::kDisplayWidth> scanline{};

    for (int y = 0; y < kade_body_contract::kDisplayHeight; ++y) {
        uint16_t fill = kDark;
        if (y >= 24 && y < 28) fill = kLight;
        if (y >= 212 && y < 216) fill = kLight;
        if (completed && y >= 112 && y < 128) fill = kAccent;
        scanline.fill(fill);
        if (esp_lcd_panel_draw_bitmap(g_probe8_surface.panel,
                                      0,
                                      y,
                                      kade_body_contract::kDisplayWidth,
                                      y + 1,
                                      scanline.data()) != ESP_OK) {
            return false;
        }
    }

    if (!probe8_set_backlight(55)) return false;
    return true;
}

bool probe8_initialise_touch()
{
    g_probe8_surface.touch = add_i2c_device(kP8TouchAddress);
    if (g_probe8_surface.touch == nullptr) return false;

    uint8_t chip_id = 0;
    if (!probe8_try_read(g_probe8_surface.touch, 0xA3, &chip_id)) return false;

    g_probe8_surface.touch_ready = true;
    ESP_LOGI(kLogTag, "PROBE8 checkpoint-health endpoint=ready id=0x%02X", chip_id);
    return true;
}

bool probe8_touch_health(const char* label)
{
    if (!g_probe8_surface.touch_ready || g_probe8_surface.touch == nullptr) return false;

    uint8_t points = 0;
    if (!probe8_try_read(g_probe8_surface.touch, 0x02, &points)) {
        ESP_LOGE(kLogTag, "PROBE8 %s status=failed stage=health-read", label);
        return false;
    }

    points &= 0x0F;
    if (points > 2) {
        ESP_LOGE(kLogTag, "PROBE8 %s status=failed stage=health-range value=%u", label, points);
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE8 %s status=ok", label);
    return true;
}

bool probe8_run_duplex_sequence()
{
    bool input_open = false;
    bool output_open = false;

    if (!initialise_transport()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=transport-init");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE8 phase=stage-a");
    if (!open_input()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-a-open");
        return false;
    }
    input_open = true;

    if (!sample_input("stage-a")) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-a-sample");
        close_input();
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(100));

    ESP_LOGI(kLogTag, "PROBE8 phase=stage-b");
    if (!open_output()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-b-open");
        close_input();
        return false;
    }
    output_open = true;

    if (!run_output()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-b-run");
        if (output_open) close_output();
        if (input_open) close_input();
        return false;
    }

    if (!close_output()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-b-close");
        if (input_open) close_input();
        return false;
    }
    output_open = false;

    vTaskDelay(pdMS_TO_TICKS(150));

    ESP_LOGI(kLogTag, "PROBE8 phase=stage-c");
    if (!sample_input("stage-c")) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-c-sample");
        if (input_open) close_input();
        return false;
    }

    if (!close_input()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=stage-c-close");
        return false;
    }

    return true;
}

bool run_probe8()
{
    ESP_LOGI(kLogTag, "PROBE8 phase=control");
    initialise_control_bus();

    ESP_LOGI(kLogTag, "PROBE8 phase=surface");
    if (!probe8_initialise_panel()) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=surface-init");
        return false;
    }
    if (!probe8_draw_frame(false)) {
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
    if (!probe8_draw_frame(true)) {
        ESP_LOGE(kLogTag, "PROBE8 status=failed stage=surface-frame-b");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE8 status=complete sequence=coordinated one_shot=1");
    return true;
}

void probe8_log_contract()
{
    using namespace kade_body_contract;
    ESP_LOGI(kLogTag,
             "BODY_CONTRACT protocol=1 display=%dx%d audio=%dHz/%dch yaw=[%d,%d] pitch=[%d,%d] speed=[%d,%d] tolerance=%d",
             kDisplayWidth, kDisplayHeight, kAudioSampleRateHz, kAudioChannels,
             kSafeYawMinTenths, kSafeYawMaxTenths, kSafePitchMinTenths, kSafePitchMaxTenths,
             kMinMotionSpeed, kMaxMotionSpeed, kPositionToleranceTenths);
    ESP_LOGI(kLogTag,
             "BODY_POLICY preserve_zero=%d release_torque=%d network=off one_shot=1",
             kPreserveStoredZeroCalibration ? 1 : 0,
             kReleaseTorqueAfterMotion ? 1 : 0);
}

}  // namespace

#ifndef KADE_PROBE8_NO_APP_MAIN
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

    const bool passed = run_probe8();

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
#endif
