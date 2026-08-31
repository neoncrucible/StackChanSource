#include "body_contract.h"

#include <cinttypes>
#include <cstdio>

#include "driver/i2c_master.h"
#include "esp_app_desc.h"
#include "esp_err.h"
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
constexpr int kProbeTimeoutMs = 40;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint8_t kAw9523Address = 0x58;

struct ProbeHardware {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t pmic = nullptr;
    i2c_master_dev_handle_t io_expander = nullptr;
};

ProbeHardware g_probe;

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

i2c_master_dev_handle_t add_i2c_device(uint8_t address)
{
    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = address;
    config.scl_speed_hz = 400000;

    i2c_master_dev_handle_t handle = nullptr;
    ESP_ERROR_CHECK(i2c_master_bus_add_device(g_probe.i2c_bus, &config, &handle));
    return handle;
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

void initialise_control_bus()
{
    i2c_master_bus_config_t config{};
    config.i2c_port = I2C_NUM_1;
    config.sda_io_num = kI2cSda;
    config.scl_io_num = kI2cScl;
    config.clk_source = I2C_CLK_SRC_DEFAULT;
    config.glitch_ignore_cnt = 7;
    config.flags.enable_internal_pullup = true;
    ESP_ERROR_CHECK(i2c_new_master_bus(&config, &g_probe.i2c_bus));

    g_probe.pmic = add_i2c_device(kAxp2101Address);
    g_probe.io_expander = add_i2c_device(kAw9523Address);

    // Exact CoreS3 rail setup inherited from the physically proven Alpha 2 board path.
    uint8_t rail = read_reg(g_probe.pmic, 0x90);
    write_reg(g_probe.pmic, 0x90, rail | 0xB4);
    write_reg(g_probe.pmic, 0x97, 28);
    write_reg(g_probe.pmic, 0x69, 0x35);
    write_reg(g_probe.pmic, 0x30, 0x3F);
    write_reg(g_probe.pmic, 0x90, 0xBF);
    write_reg(g_probe.pmic, 0x94, 28);
    write_reg(g_probe.pmic, 0x95, 28);
    write_reg(g_probe.pmic, 0x27, 0x00);

    // This probe owns no display, so keep the display rail dark.
    rail = read_reg(g_probe.pmic, 0x90);
    write_reg(g_probe.pmic, 0x90, rail & 0x7F);

    // Exact expander baseline inherited from the physically proven Alpha 2 board path.
    write_reg(g_probe.io_expander, 0x02, 0x07);
    write_reg(g_probe.io_expander, 0x03, 0x8F);
    write_reg(g_probe.io_expander, 0x04, 0x18);
    write_reg(g_probe.io_expander, 0x05, 0x0C);
    write_reg(g_probe.io_expander, 0x11, 0x10);
    write_reg(g_probe.io_expander, 0x12, 0xFF);
    write_reg(g_probe.io_expander, 0x13, 0xFF);
}

void prepare_next_endpoint()
{
    // Exact reset sequence used by the signed-off Alpha 2 board path.
    write_reg(g_probe.io_expander, 0x02, 0x03);
    vTaskDelay(pdMS_TO_TICKS(10));
    write_reg(g_probe.io_expander, 0x02, 0x07);
    vTaskDelay(pdMS_TO_TICKS(50));
}

int scan_control_bus()
{
    int found = 0;
    for (uint8_t address = 0x08; address <= 0x77; ++address) {
        const esp_err_t err = i2c_master_probe(g_probe.i2c_bus, address, kProbeTimeoutMs);
        if (err == ESP_OK) {
            ++found;
            ESP_LOGI(kLogTag, "PROBE3_DEVICE address=0x%02X", address);
        } else if (err != ESP_ERR_NOT_FOUND && err != ESP_ERR_TIMEOUT) {
            ESP_LOGW(kLogTag, "PROBE3_SCAN address=0x%02X err=%s", address, esp_err_to_name(err));
        }
    }
    return found;
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
             "BODY_POLICY preserve_zero=%d release_torque=%d motion_driver=off display_driver=off data_path=off network=off",
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

    ESP_LOGI(kLogTag, "PROBE3 phase=control-bus");
    initialise_control_bus();
    ESP_LOGI(kLogTag, "PROBE3 phase=endpoint");
    prepare_next_endpoint();
    const int devices = scan_control_bus();
    ESP_LOGI(kLogTag, "PROBE3 status=ready devices=%d", devices);

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
