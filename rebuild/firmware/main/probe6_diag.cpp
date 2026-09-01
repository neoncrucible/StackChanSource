#include "body_contract.h"

#include <array>
#include <cinttypes>
#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "driver/i2c_master.h"
#include "driver/uart.h"
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
constexpr int kIoTimeoutMs = 25;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kPowerExpanderAddress = 0x6F;
constexpr uint8_t kRegVersion = 0x02;
constexpr uint8_t kRegGpioModeLow = 0x03;
constexpr uint8_t kRegGpioOutputLow = 0x05;
constexpr uint8_t kRegGpioPullUpLow = 0x09;
constexpr uint8_t kRegGpioPullDownLow = 0x0B;
constexpr uint8_t kPowerPinMask = 0x01;

constexpr uart_port_t kServoUart = UART_NUM_1;
constexpr int kServoBaud = 1000000;
constexpr gpio_num_t kServoTx = GPIO_NUM_6;
constexpr gpio_num_t kServoRx = GPIO_NUM_7;
constexpr uint8_t kPrimaryId = 1;
constexpr uint8_t kSecondaryId = 2;
constexpr uint8_t kBroadcastId = 0xFE;

constexpr uint8_t kInstructionRead = 0x02;
constexpr uint8_t kInstructionWrite = 0x03;
constexpr uint8_t kRegTorqueEnable = 40;
constexpr uint8_t kRegPresentPosition = 56;

struct Runtime {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t power_expander = nullptr;
    bool power_control_ready = false;
    bool uart_ready = false;
    bool power_enabled = false;
    bool complete = false;
};

Runtime g_runtime;

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

bool i2c_read_reg(uint8_t reg, uint8_t* value)
{
    if (g_runtime.power_expander == nullptr || value == nullptr) return false;
    return i2c_master_transmit_receive(
               g_runtime.power_expander, &reg, 1, value, 1, kI2cTimeoutMs) == ESP_OK;
}

bool i2c_write_reg(uint8_t reg, uint8_t value)
{
    if (g_runtime.power_expander == nullptr) return false;
    const uint8_t payload[2] = {reg, value};
    return i2c_master_transmit(
               g_runtime.power_expander, payload, sizeof(payload), kI2cTimeoutMs) == ESP_OK;
}

bool i2c_update_bit(uint8_t reg, uint8_t mask, bool enabled)
{
    uint8_t value = 0;
    if (!i2c_read_reg(reg, &value)) return false;
    value = enabled ? static_cast<uint8_t>(value | mask)
                    : static_cast<uint8_t>(value & static_cast<uint8_t>(~mask));
    return i2c_write_reg(reg, value);
}

bool initialise_power_control()
{
    i2c_master_bus_config_t bus_cfg{};
    bus_cfg.i2c_port = I2C_NUM_1;
    bus_cfg.sda_io_num = kI2cSda;
    bus_cfg.scl_io_num = kI2cScl;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;

    esp_err_t err = i2c_new_master_bus(&bus_cfg, &g_runtime.i2c_bus);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=control-bus err=%s", esp_err_to_name(err));
        return false;
    }

    i2c_device_config_t dev_cfg{};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = kPowerExpanderAddress;
    dev_cfg.scl_speed_hz = 100000;
    err = i2c_master_bus_add_device(g_runtime.i2c_bus, &dev_cfg, &g_runtime.power_expander);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=control-endpoint err=%s", esp_err_to_name(err));
        return false;
    }

    uint8_t version = 0;
    if (!i2c_read_reg(kRegVersion, &version) || version == 0 || version == 0xFF) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=control-version");
        return false;
    }
    ESP_LOGI(kLogTag, "PROBE6D control-version=0x%02X", version);

    if (!i2c_update_bit(kRegGpioModeLow, kPowerPinMask, true) ||
        !i2c_update_bit(kRegGpioPullDownLow, kPowerPinMask, false) ||
        !i2c_update_bit(kRegGpioPullUpLow, kPowerPinMask, true)) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=control-config");
        return false;
    }

    g_runtime.power_control_ready = true;
    return true;
}

bool set_power_enabled(bool enabled)
{
    if (!g_runtime.power_control_ready) return false;
    if (!i2c_update_bit(kRegGpioOutputLow, kPowerPinMask, enabled)) return false;
    g_runtime.power_enabled = enabled;
    return true;
}

bool initialise_uart()
{
    uart_config_t uart_cfg{};
    uart_cfg.baud_rate = kServoBaud;
    uart_cfg.data_bits = UART_DATA_8_BITS;
    uart_cfg.parity = UART_PARITY_DISABLE;
    uart_cfg.stop_bits = UART_STOP_BITS_1;
    uart_cfg.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    uart_cfg.rx_flow_ctrl_thresh = 0;
    uart_cfg.source_clk = UART_SCLK_DEFAULT;

    esp_err_t err = uart_driver_install(kServoUart, 1024, 1024, 0, nullptr, 0);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=transport-install err=%s", esp_err_to_name(err));
        return false;
    }
    err = uart_param_config(kServoUart, &uart_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=transport-config err=%s", esp_err_to_name(err));
        uart_driver_delete(kServoUart);
        return false;
    }
    err = uart_set_pin(kServoUart, kServoTx, kServoRx, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=transport-pins err=%s", esp_err_to_name(err));
        uart_driver_delete(kServoUart);
        return false;
    }
    g_runtime.uart_ready = true;
    return true;
}

bool uart_read_exact(uint8_t* data, std::size_t length, int64_t deadline_us)
{
    std::size_t offset = 0;
    while (offset < length && esp_timer_get_time() < deadline_us) {
        const int count = uart_read_bytes(
            kServoUart, data + offset, static_cast<uint32_t>(length - offset), 0);
        if (count > 0) {
            offset += static_cast<std::size_t>(count);
        } else {
            vTaskDelay(pdMS_TO_TICKS(1));
        }
    }
    return offset == length;
}

bool uart_find_header(int64_t deadline_us)
{
    uint8_t previous = 0;
    while (esp_timer_get_time() < deadline_us) {
        uint8_t current = 0;
        if (!uart_read_exact(&current, 1, deadline_us)) return false;
        if (previous == 0xFF && current == 0xFF) return true;
        previous = current;
    }
    return false;
}

bool read_response(uint8_t expected_id, uint8_t* payload, std::size_t expected_payload)
{
    const int64_t deadline_us = esp_timer_get_time() + static_cast<int64_t>(kIoTimeoutMs) * 1000;
    if (!uart_find_header(deadline_us)) return false;

    uint8_t header[3]{};
    if (!uart_read_exact(header, sizeof(header), deadline_us)) return false;
    const uint8_t response_id = header[0];
    const uint8_t length = header[1];
    const uint8_t status = header[2];
    if (response_id != expected_id || length != expected_payload + 2 || status != 0) return false;

    std::array<uint8_t, 8> data{};
    if (expected_payload > data.size()) return false;
    if (expected_payload > 0 && !uart_read_exact(data.data(), expected_payload, deadline_us)) return false;

    uint8_t checksum = 0;
    if (!uart_read_exact(&checksum, 1, deadline_us)) return false;

    uint8_t sum = static_cast<uint8_t>(response_id + length + status);
    for (std::size_t i = 0; i < expected_payload; ++i) {
        sum = static_cast<uint8_t>(sum + data[i]);
    }
    if (checksum != static_cast<uint8_t>(~sum)) return false;

    if (payload != nullptr) {
        for (std::size_t i = 0; i < expected_payload; ++i) payload[i] = data[i];
    }
    return true;
}

bool send_read_request(uint8_t id, uint8_t address, uint8_t requested_length)
{
    const uint8_t protocol_length = 4;
    std::array<uint8_t, 8> packet{};
    packet[0] = 0xFF;
    packet[1] = 0xFF;
    packet[2] = id;
    packet[3] = protocol_length;
    packet[4] = kInstructionRead;
    packet[5] = address;
    packet[6] = requested_length;
    const uint8_t sum = static_cast<uint8_t>(id + protocol_length + kInstructionRead + address + requested_length);
    packet[7] = static_cast<uint8_t>(~sum);

    uart_flush_input(kServoUart);
    if (uart_write_bytes(kServoUart, reinterpret_cast<const char*>(packet.data()), packet.size()) !=
        static_cast<int>(packet.size())) return false;
    return uart_wait_tx_done(kServoUart, pdMS_TO_TICKS(100)) == ESP_OK;
}

bool read_register(uint8_t id, uint8_t address, uint8_t* output, std::size_t length)
{
    if (!g_runtime.uart_ready || output == nullptr || length == 0 || length > 8) return false;
    if (!send_read_request(id, address, static_cast<uint8_t>(length))) return false;
    return read_response(id, output, length);
}

bool write_register_byte(uint8_t id, uint8_t address, uint8_t value, bool expect_ack)
{
    const uint8_t protocol_length = 4;
    std::array<uint8_t, 8> packet{};
    packet[0] = 0xFF;
    packet[1] = 0xFF;
    packet[2] = id;
    packet[3] = protocol_length;
    packet[4] = kInstructionWrite;
    packet[5] = address;
    packet[6] = value;
    const uint8_t sum = static_cast<uint8_t>(id + protocol_length + kInstructionWrite + address + value);
    packet[7] = static_cast<uint8_t>(~sum);

    uart_flush_input(kServoUart);
    if (uart_write_bytes(kServoUart, reinterpret_cast<const char*>(packet.data()), packet.size()) !=
        static_cast<int>(packet.size())) return false;
    if (uart_wait_tx_done(kServoUart, pdMS_TO_TICKS(100)) != ESP_OK) return false;
    return !expect_ack || read_response(id, nullptr, 0);
}

bool read_position(uint8_t id, int* position)
{
    if (position == nullptr) return false;
    uint8_t data[2]{};
    if (!read_register(id, kRegPresentPosition, data, sizeof(data))) return false;
    *position = (static_cast<int>(data[0]) << 8) | data[1];
    return *position >= 0 && *position <= 1000;
}

bool read_torque(uint8_t id, int* enabled)
{
    if (enabled == nullptr) return false;
    uint8_t data = 0;
    if (!read_register(id, kRegTorqueEnable, &data, 1)) return false;
    *enabled = static_cast<int>(data);
    return true;
}

void broadcast_release()
{
    if (g_runtime.uart_ready) {
        write_register_byte(kBroadcastId, kRegTorqueEnable, 0, false);
    }
}

void safe_shutdown()
{
    broadcast_release();
    if (g_runtime.power_control_ready && g_runtime.power_enabled) {
        set_power_enabled(false);
    }
}

bool run_diagnostic()
{
    ESP_LOGI(kLogTag, "PROBE6D phase=control-bus");
    if (!initialise_power_control()) return false;
    if (!set_power_enabled(true)) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=control-enable");
        return false;
    }

    // Mirror the proven factory ordering more closely: power is established and
    // allowed to settle before the transport is opened or the first request is sent.
    vTaskDelay(pdMS_TO_TICKS(650));

    if (!initialise_uart()) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=transport-init");
        safe_shutdown();
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(100));

    ESP_LOGI(kLogTag, "PROBE6D phase=readback");
    int primary_position = -1;
    int secondary_position = -1;
    const bool primary_read = read_position(kPrimaryId, &primary_position);
    const bool secondary_read = read_position(kSecondaryId, &secondary_position);
    ESP_LOGI(kLogTag,
             "PROBE6D readback primary_ok=%d primary_pos=%d secondary_ok=%d secondary_pos=%d",
             primary_read ? 1 : 0,
             primary_position,
             secondary_read ? 1 : 0,
             secondary_position);

    ESP_LOGI(kLogTag, "PROBE6D phase=safe-write");
    const bool primary_release = write_register_byte(kPrimaryId, kRegTorqueEnable, 0, true);
    const bool secondary_release = write_register_byte(kSecondaryId, kRegTorqueEnable, 0, true);
    broadcast_release();
    ESP_LOGI(kLogTag,
             "PROBE6D release primary_ack=%d secondary_ack=%d",
             primary_release ? 1 : 0,
             secondary_release ? 1 : 0);

    int primary_torque = -1;
    int secondary_torque = -1;
    const bool primary_torque_read = read_torque(kPrimaryId, &primary_torque);
    const bool secondary_torque_read = read_torque(kSecondaryId, &secondary_torque);
    ESP_LOGI(kLogTag,
             "PROBE6D verify primary_ok=%d primary_torque=%d secondary_ok=%d secondary_torque=%d",
             primary_torque_read ? 1 : 0,
             primary_torque,
             secondary_torque_read ? 1 : 0,
             secondary_torque);

    const bool passed = primary_read && secondary_read &&
                        primary_release && secondary_release &&
                        primary_torque_read && secondary_torque_read &&
                        primary_torque == 0 && secondary_torque == 0;

    safe_shutdown();
    if (!passed) {
        ESP_LOGE(kLogTag, "PROBE6D status=failed stage=handshake");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE6D status=complete active_stage=not-entered preserve_zero=1");
    return true;
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
             "BODY_POLICY preserve_zero=%d release_torque=%d active_stage=off display_driver=off input_path=off output_path=off network=off",
             kPreserveStoredZeroCalibration ? 1 : 0,
             kReleaseTorqueAfterMotion ? 1 : 0);
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));

    ESP_LOGI(kLogTag,
             "BODY_BOOT firmware=%s device_id=%s reset=%s",
             esp_app_get_description()->version,
             device_id,
             reset_reason_name(esp_reset_reason()));
    log_contract();

    const bool passed = run_diagnostic();
    g_runtime.complete = passed;

    uint32_t sequence = 0;
    const int64_t start_us = esp_timer_get_time();
    while (true) {
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIi64 " free_heap=%u status=%s",
                 sequence++,
                 (esp_timer_get_time() - start_us) / 1000,
                 static_cast<unsigned>(esp_get_free_heap_size()),
                 g_runtime.complete ? "diagnostic-complete" : "diagnostic-failed");
        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
