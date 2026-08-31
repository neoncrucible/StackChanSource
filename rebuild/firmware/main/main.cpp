#include "body_contract.h"

#include <array>
#include <cinttypes>
#include <cstdio>

#include "driver/i2c_master.h"
#include "driver/spi_master.h"
#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

constexpr const char* kLogTag = "KADE-BODY";
constexpr uint32_t kHeartbeatMs = 5000;
constexpr int kI2cTimeoutMs = 250;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint8_t kAw9523Address = 0x58;

constexpr gpio_num_t kLcdMosi = GPIO_NUM_37;
constexpr gpio_num_t kLcdClock = GPIO_NUM_36;
constexpr gpio_num_t kLcdCs = GPIO_NUM_3;
constexpr gpio_num_t kLcdDc = GPIO_NUM_35;
constexpr spi_host_device_t kLcdHost = SPI3_HOST;

struct DisplayHardware {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t pmic = nullptr;
    i2c_master_dev_handle_t io_expander = nullptr;
    esp_lcd_panel_io_handle_t panel_io = nullptr;
    esp_lcd_panel_handle_t panel = nullptr;
};

DisplayHardware g_display;

const char* reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
        case ESP_RST_POWERON: return "power-on";
        case ESP_RST_EXT: return "external-reset";
        case ESP_RST_SW: return "software-reset";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt-watchdog";
        case ESP_RST_TASK_WDT: return "task-watchdog";
        case ESP_RST_WDT: return "other-watchdog";
        case ESP_RST_DEEPSLEEP: return "deep-sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        case ESP_RST_UNKNOWN:
        default: return "unknown-or-other";
    }
}

void make_device_id(char* output, std::size_t output_size)
{
    uint8_t mac[6]{};
    if (esp_efuse_mac_get_default(mac) != ESP_OK) {
        std::snprintf(output, output_size, "esp32s3-unknown");
        return;
    }

    std::snprintf(output,
                  output_size,
                  "esp32s3-%02X%02X%02X%02X%02X%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void write_reg(i2c_master_dev_handle_t device, uint8_t reg, uint8_t value)
{
    const uint8_t payload[2] = {reg, value};
    ESP_ERROR_CHECK(i2c_master_transmit(device, payload, sizeof(payload), kI2cTimeoutMs));
}

uint8_t read_reg(i2c_master_dev_handle_t device, uint8_t reg)
{
    uint8_t value = 0;
    ESP_ERROR_CHECK(i2c_master_transmit_receive(device, &reg, 1, &value, 1, kI2cTimeoutMs));
    return value;
}

i2c_master_dev_handle_t add_i2c_device(uint8_t address)
{
    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = address;
    config.scl_speed_hz = 400000;

    i2c_master_dev_handle_t handle = nullptr;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_display.i2c_bus, &config, &handle));
    return handle;
}

void initialise_display_power()
{
    i2c_master_bus_config_t bus_config{};
    bus_config.i2c_port = I2C_NUM_1;
    bus_config.sda_io_num = kI2cSda;
    bus_config.scl_io_num = kI2cScl;
    bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_config.glitch_ignore_cnt = 7;
    bus_config.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_config, &g_display.i2c_bus));

    g_display.pmic = add_i2c_device(kAxp2101Address);
    g_display.io_expander = add_i2c_device(kAw9523Address);

    // Proven CoreS3 power rail setup from the physically signed-off Alpha 2 path.
    uint8_t rail = read_reg(g_display.pmic, 0x90);
    write_reg(g_display.pmic, 0x90, rail | 0xB4);
    write_reg(g_display.pmic, 0x97, 28);
    write_reg(g_display.pmic, 0x69, 0x35);
    write_reg(g_display.pmic, 0x30, 0x3F);
    write_reg(g_display.pmic, 0x90, 0xBF);
    write_reg(g_display.pmic, 0x94, 28);
    write_reg(g_display.pmic, 0x95, 28);
    write_reg(g_display.pmic, 0x27, 0x00);

    // Keep the backlight dark until the panel has a complete deterministic frame.
    rail = read_reg(g_display.pmic, 0x90);
    write_reg(g_display.pmic, 0x90, rail & 0x7F);

    // Proven AW9523 setup. No audio, servo or touch services are enabled here.
    write_reg(g_display.io_expander, 0x02, 0x07);
    write_reg(g_display.io_expander, 0x03, 0x8F);
    write_reg(g_display.io_expander, 0x04, 0x18);
    write_reg(g_display.io_expander, 0x05, 0x0C);
    write_reg(g_display.io_expander, 0x11, 0x10);
    write_reg(g_display.io_expander, 0x12, 0xFF);
    write_reg(g_display.io_expander, 0x13, 0xFF);
}

void reset_panel_via_expander()
{
    write_reg(g_display.io_expander, 0x03, 0x81);
    vTaskDelay(pdMS_TO_TICKS(20));
    write_reg(g_display.io_expander, 0x03, 0x83);
    vTaskDelay(pdMS_TO_TICKS(10));
}

void set_backlight(uint8_t percent)
{
    if (percent > 100) percent = 100;
    if (percent == 0) {
        const uint8_t rail = read_reg(g_display.pmic, 0x90);
        write_reg(g_display.pmic, 0x90, rail & 0x7F);
        return;
    }

    const uint8_t register_value = static_cast<uint8_t>(20 + (static_cast<uint16_t>(percent) * 8 / 100));
    write_reg(g_display.pmic, 0x99, register_value);
    const uint8_t rail = read_reg(g_display.pmic, 0x90);
    write_reg(g_display.pmic, 0x90, rail | 0x80);
}

void initialise_panel()
{
    spi_bus_config_t bus_config{};
    bus_config.mosi_io_num = kLcdMosi;
    bus_config.miso_io_num = GPIO_NUM_NC;
    bus_config.sclk_io_num = kLcdClock;
    bus_config.quadwp_io_num = GPIO_NUM_NC;
    bus_config.quadhd_io_num = GPIO_NUM_NC;
    bus_config.max_transfer_sz = kade_body_contract::kDisplayWidth *
                                 kade_body_contract::kDisplayHeight *
                                 static_cast<int>(sizeof(uint16_t));
    ESP_ERROR_CHECK(spi_bus_initialize(kLcdHost, &bus_config, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_spi_config_t io_config{};
    io_config.cs_gpio_num = kLcdCs;
    io_config.dc_gpio_num = kLcdDc;
    io_config.spi_mode = 2;
    io_config.pclk_hz = 40 * 1000 * 1000;
    io_config.trans_queue_depth = 10;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(kLcdHost, &io_config, &g_display.panel_io));

    esp_lcd_panel_dev_config_t panel_config{};
    panel_config.reset_gpio_num = GPIO_NUM_NC;
    panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_BGR;
    panel_config.bits_per_pixel = 16;
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(g_display.panel_io, &panel_config, &g_display.panel));

    ESP_ERROR_CHECK(esp_lcd_panel_reset(g_display.panel));
    reset_panel_via_expander();
    ESP_ERROR_CHECK(esp_lcd_panel_init(g_display.panel));
    ESP_ERROR_CHECK(esp_lcd_panel_invert_color(g_display.panel, true));
    ESP_ERROR_CHECK(esp_lcd_panel_swap_xy(g_display.panel, false));
    ESP_ERROR_CHECK(esp_lcd_panel_mirror(g_display.panel, false, false));

    const esp_err_t display_on = esp_lcd_panel_disp_on_off(g_display.panel, true);
    if (display_on != ESP_OK && display_on != ESP_ERR_NOT_SUPPORTED) {
        ESP_ERROR_CHECK(display_on);
    }
}

void draw_display_probe()
{
    constexpr std::array<uint16_t, 4> colours = {
        0xF800,  // primary 1
        0x07E0,  // primary 2
        0x001F,  // primary 3
        0xFFFF,  // white
    };

    std::array<uint16_t, kade_body_contract::kDisplayWidth> scanline{};
    const int band_height = kade_body_contract::kDisplayHeight / static_cast<int>(colours.size());

    for (int band = 0; band < static_cast<int>(colours.size()); ++band) {
        scanline.fill(colours[band]);
        const int y0 = band * band_height;
        const int y1 = (band == static_cast<int>(colours.size()) - 1)
                           ? kade_body_contract::kDisplayHeight
                           : y0 + band_height;
        for (int y = y0; y < y1; ++y) {
            ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(
                g_display.panel,
                0,
                y,
                kade_body_contract::kDisplayWidth,
                y + 1,
                scanline.data()));
        }
    }

    set_backlight(65);
    ESP_LOGI(kLogTag, "DISPLAY_PROBE status=ready pattern=four-bars backlight=65");
}

void log_contract()
{
    using namespace kade_body_contract;
    ESP_LOGI(kLogTag,
             "BODY_CONTRACT protocol=1 display=%dx%d audio=%dHz/%dch yaw=[%d,%d] pitch=[%d,%d] speed=[%d,%d] tolerance=%d",
             kDisplayWidth, kDisplayHeight, kAudioSampleRateHz, kAudioChannels,
             kSafeYawMinTenths, kSafeYawMaxTenths, kSafePitchMinTenths, kSafePitchMaxTenths,
             kMinMotionSpeed, kMaxMotionSpeed, kPositionToleranceTenths);
    ESP_LOGI(kLogTag,
             "BODY_POLICY preserve_zero=%d release_torque=%d motion_driver=off audio_driver=off display_driver=probe network=off",
             kPreserveStoredZeroCalibration ? 1 : 0,
             kReleaseTorqueAfterMotion ? 1 : 0);
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

    ESP_LOGI(kLogTag, "DISPLAY_PROBE phase=power");
    initialise_display_power();
    ESP_LOGI(kLogTag, "DISPLAY_PROBE phase=panel");
    initialise_panel();
    ESP_LOGI(kLogTag, "DISPLAY_PROBE phase=draw");
    draw_display_probe();

    uint32_t sequence = 0;
    while (true) {
        const uint64_t uptime_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        const uint32_t free_heap = esp_get_free_heap_size();
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu64 " free_heap=%" PRIu32,
                 sequence++, uptime_ms, free_heap);
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
