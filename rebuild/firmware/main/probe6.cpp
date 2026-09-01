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
#include "nvs.h"
#include "nvs_flash.h"

namespace {

constexpr const char* kLogTag = "KADE-BODY";
constexpr uint32_t kHeartbeatMs = 5000;
constexpr int kIoTimeoutMs = 20;
constexpr int kI2cTimeoutMs = 250;
constexpr int kSettlePollMs = 50;
constexpr int kRampPeriodMs = 20;
constexpr int kRampStepTenths = 10;
constexpr int kProbeOffsetTenths = 100;
constexpr int kMoveTimeoutMs = 4500;
constexpr int kReturnTimeoutMs = 7000;
constexpr int kHoldMs = 500;
constexpr int kServoCommandTime = 20;

constexpr uart_port_t kServoUart = UART_NUM_1;
constexpr int kServoBaud = 1000000;
constexpr gpio_num_t kServoTx = GPIO_NUM_6;
constexpr gpio_num_t kServoRx = GPIO_NUM_7;
constexpr uint8_t kPrimaryId = 1;
constexpr uint8_t kSecondaryId = 2;
constexpr uint8_t kBroadcastId = 0xFE;

constexpr gpio_num_t kI2cSda = GPIO_NUM_12;
constexpr gpio_num_t kI2cScl = GPIO_NUM_11;
constexpr uint8_t kPowerExpanderAddress = 0x6F;
constexpr uint8_t kRegVersion = 0x02;
constexpr uint8_t kRegGpioModeLow = 0x03;
constexpr uint8_t kRegGpioOutputLow = 0x05;
constexpr uint8_t kRegGpioPullUpLow = 0x09;
constexpr uint8_t kRegGpioPullDownLow = 0x0B;
constexpr uint8_t kPowerPinMask = 0x01;

constexpr uint8_t kInstructionRead = 0x02;
constexpr uint8_t kInstructionWrite = 0x03;
constexpr uint8_t kRegTorqueEnable = 40;
constexpr uint8_t kRegGoalPosition = 42;
constexpr uint8_t kRegPresentPosition = 56;
constexpr uint8_t kRegMoving = 66;
constexpr int kRawPositionMin = 0;
constexpr int kRawPositionMax = 1000;

static_assert(kade_body_contract::kPreserveStoredZeroCalibration);
static_assert(kade_body_contract::kReleaseTorqueAfterMotion);
static_assert(kProbeOffsetTenths > 0);
static_assert(kProbeOffsetTenths <=
              (kade_body_contract::kSafeYawMaxTenths - kade_body_contract::kSafeYawMinTenths));
static_assert(kade_body_contract::kDefaultMotionSpeed >= kade_body_contract::kMinMotionSpeed);
static_assert(kade_body_contract::kDefaultMotionSpeed <= kade_body_contract::kMaxMotionSpeed);

struct Runtime {
    i2c_master_bus_handle_t i2c_bus = nullptr;
    i2c_master_dev_handle_t power_expander = nullptr;
    bool power_control_ready = false;
    bool uart_ready = false;
    bool power_enabled = false;
    bool failed = false;
};

Runtime g_runtime;

int abs_int(int value)
{
    return value < 0 ? -value : value;
}

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
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=control-bus err=%s", esp_err_to_name(err));
        return false;
    }

    i2c_device_config_t dev_cfg{};
    dev_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    dev_cfg.device_address = kPowerExpanderAddress;
    dev_cfg.scl_speed_hz = 100000;
    err = i2c_master_bus_add_device(g_runtime.i2c_bus, &dev_cfg, &g_runtime.power_expander);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=control-endpoint err=%s", esp_err_to_name(err));
        return false;
    }

    uint8_t version = 0;
    if (!i2c_read_reg(kRegVersion, &version) || version == 0 || version == 0xFF) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=control-version");
        return false;
    }

    if (!i2c_update_bit(kRegGpioModeLow, kPowerPinMask, true) ||
        !i2c_update_bit(kRegGpioPullDownLow, kPowerPinMask, false) ||
        !i2c_update_bit(kRegGpioPullUpLow, kPowerPinMask, true)) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=control-config");
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

    esp_err_t err = uart_driver_install(kServoUart, 256, 256, 0, nullptr, 0);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=transport-install err=%s", esp_err_to_name(err));
        return false;
    }
    err = uart_param_config(kServoUart, &uart_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=transport-config err=%s", esp_err_to_name(err));
        uart_driver_delete(kServoUart);
        return false;
    }
    err = uart_set_pin(kServoUart, kServoTx, kServoRx, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag, "PROBE6 status=failed stage=transport-pins err=%s", esp_err_to_name(err));
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
            continue;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
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

bool send_packet(uint8_t id,
                 uint8_t instruction,
                 uint8_t memory_address,
                 const uint8_t* data,
                 std::size_t data_length,
                 bool expect_ack)
{
    if (!g_runtime.uart_ready || data_length > 8) return false;

    std::array<uint8_t, 16> packet{};
    const uint8_t protocol_length = static_cast<uint8_t>(data_length + 3);
    packet[0] = 0xFF;
    packet[1] = 0xFF;
    packet[2] = id;
    packet[3] = protocol_length;
    packet[4] = instruction;
    packet[5] = memory_address;

    uint8_t sum = static_cast<uint8_t>(id + protocol_length + instruction + memory_address);
    for (std::size_t i = 0; i < data_length; ++i) {
        packet[6 + i] = data[i];
        sum = static_cast<uint8_t>(sum + data[i]);
    }
    packet[6 + data_length] = static_cast<uint8_t>(~sum);
    const std::size_t packet_length = 7 + data_length;

    uart_flush_input(kServoUart);
    const int written = uart_write_bytes(
        kServoUart, reinterpret_cast<const char*>(packet.data()), packet_length);
    if (written != static_cast<int>(packet_length)) return false;
    if (uart_wait_tx_done(kServoUart, pdMS_TO_TICKS(100)) != ESP_OK) return false;

    if (!expect_ack) return true;
    return read_response(id, nullptr, 0);
}

bool write_register_byte(uint8_t id, uint8_t address, uint8_t value)
{
    return send_packet(id, kInstructionWrite, address, &value, 1, id != kBroadcastId);
}

bool read_register(uint8_t id, uint8_t address, uint8_t* output, std::size_t length)
{
    if (output == nullptr || length == 0 || length > 8) return false;
    const uint8_t requested = static_cast<uint8_t>(length);
    if (!send_packet(id, kInstructionRead, address, &requested, 1, false)) return false;
    return read_response(id, output, length);
}

bool read_raw_position(int* raw_position)
{
    if (raw_position == nullptr) return false;
    uint8_t data[2]{};
    if (!read_register(kPrimaryId, kRegPresentPosition, data, sizeof(data))) return false;
    *raw_position = (static_cast<int>(data[0]) << 8) | data[1];
    return *raw_position >= kRawPositionMin && *raw_position <= kRawPositionMax;
}

bool read_moving(bool* moving)
{
    if (moving == nullptr) return false;
    uint8_t value = 0;
    if (!read_register(kPrimaryId, kRegMoving, &value, 1)) return false;
    *moving = value != 0;
    return true;
}

bool write_raw_position(int raw_position)
{
    if (raw_position < kRawPositionMin || raw_position > kRawPositionMax) return false;
    const uint16_t position = static_cast<uint16_t>(raw_position);
    const uint16_t command_time = static_cast<uint16_t>(kServoCommandTime);
    const uint16_t speed = 0;
    const uint8_t data[6] = {
        static_cast<uint8_t>((position >> 8) & 0xFF),
        static_cast<uint8_t>(position & 0xFF),
        static_cast<uint8_t>((command_time >> 8) & 0xFF),
        static_cast<uint8_t>(command_time & 0xFF),
        static_cast<uint8_t>((speed >> 8) & 0xFF),
        static_cast<uint8_t>(speed & 0xFF),
    };
    return send_packet(kPrimaryId, kInstructionWrite, kRegGoalPosition, data, sizeof(data), true);
}

bool release_torque()
{
    if (!g_runtime.uart_ready) return false;
    const bool primary_ok = write_register_byte(kPrimaryId, kRegTorqueEnable, 0);
    const bool secondary_ok = write_register_byte(kSecondaryId, kRegTorqueEnable, 0);
    if (!primary_ok || !secondary_ok) {
        const uint8_t disabled = 0;
        send_packet(kBroadcastId, kInstructionWrite, kRegTorqueEnable, &disabled, 1, false);
    }
    return primary_ok && secondary_ok;
}

bool enable_primary_torque()
{
    return write_register_byte(kPrimaryId, kRegTorqueEnable, 1);
}

bool load_zero_position_read_only(int* zero_position)
{
    if (zero_position == nullptr) return false;

    const esp_err_t init_err = nvs_flash_init();
    if (init_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE6 status=failed stage=storage-init err=%s preserve_zero=1",
                 esp_err_to_name(init_err));
        return false;
    }

    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open("servo", NVS_READONLY, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE6 status=failed stage=storage-open err=%s preserve_zero=1",
                 esp_err_to_name(err));
        return false;
    }

    int32_t stored_zero = -1;
    err = nvs_get_i32(handle, "zero_pos_1", &stored_zero);
    nvs_close(handle);
    if (err != ESP_OK || stored_zero < kRawPositionMin || stored_zero > kRawPositionMax) {
        ESP_LOGE(kLogTag,
                 "PROBE6 status=failed stage=storage-read err=%s preserve_zero=1",
                 esp_err_to_name(err));
        return false;
    }

    *zero_position = static_cast<int>(stored_zero);
    return true;
}

int raw_to_angle_tenths(int raw_position, int zero_position)
{
    return (raw_position - zero_position) * 50 / 16;
}

bool angle_to_raw(int angle_tenths, int zero_position, int* raw_position)
{
    if (raw_position == nullptr) return false;
    if (angle_tenths < kade_body_contract::kSafeYawMinTenths ||
        angle_tenths > kade_body_contract::kSafeYawMaxTenths) {
        return false;
    }
    const int mapped = zero_position + angle_tenths * 16 / 50;
    if (mapped < kRawPositionMin || mapped > kRawPositionMax) return false;
    *raw_position = mapped;
    return true;
}

bool choose_target(int start_angle, int* target_angle)
{
    if (target_angle == nullptr) return false;
    const int positive = start_angle + kProbeOffsetTenths;
    if (positive <= kade_body_contract::kSafeYawMaxTenths) {
        *target_angle = positive;
        return true;
    }
    const int negative = start_angle - kProbeOffsetTenths;
    if (negative >= kade_body_contract::kSafeYawMinTenths) {
        *target_angle = negative;
        return true;
    }
    return false;
}

bool ramp_to_angle(int from_angle, int to_angle, int zero_position)
{
    int current = from_angle;
    while (current != to_angle) {
        const int delta = to_angle - current;
        if (delta > kRampStepTenths) {
            current += kRampStepTenths;
        } else if (delta < -kRampStepTenths) {
            current -= kRampStepTenths;
        } else {
            current = to_angle;
        }

        int raw_position = 0;
        if (!angle_to_raw(current, zero_position, &raw_position) || !write_raw_position(raw_position)) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(kRampPeriodMs));
    }
    return true;
}

bool wait_until_settled(int target_angle,
                        int zero_position,
                        int timeout_ms,
                        int* final_angle)
{
    const int64_t deadline_us = esp_timer_get_time() + static_cast<int64_t>(timeout_ms) * 1000;
    int stable_samples = 0;

    while (esp_timer_get_time() < deadline_us) {
        int raw_position = 0;
        bool moving = true;
        if (!read_raw_position(&raw_position) || !read_moving(&moving)) return false;

        const int angle = raw_to_angle_tenths(raw_position, zero_position);
        if (angle < kade_body_contract::kSafeYawMinTenths - kade_body_contract::kPositionToleranceTenths ||
            angle > kade_body_contract::kSafeYawMaxTenths + kade_body_contract::kPositionToleranceTenths) {
            return false;
        }

        if (!moving && abs_int(angle - target_angle) <= kade_body_contract::kPositionToleranceTenths) {
            ++stable_samples;
            if (stable_samples >= 2) {
                if (final_angle != nullptr) *final_angle = angle;
                return true;
            }
        } else {
            stable_samples = 0;
        }
        vTaskDelay(pdMS_TO_TICKS(kSettlePollMs));
    }
    return false;
}

void fail_closed(const char* stage)
{
    ESP_LOGE(kLogTag, "PROBE6 status=failed stage=%s", stage);
    if (g_runtime.uart_ready) release_torque();
    if (g_runtime.power_control_ready && g_runtime.power_enabled) {
        set_power_enabled(false);
    }
    g_runtime.failed = true;
}

bool run_probe()
{
    ESP_LOGI(kLogTag, "PROBE6 phase=control-bus");
    if (!initialise_power_control()) return false;
    if (!initialise_uart()) {
        fail_closed("transport-init");
        return false;
    }
    if (!set_power_enabled(true)) {
        fail_closed("control-enable");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(200));

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

void log_contract()
{
    using namespace kade_body_contract;
    ESP_LOGI(kLogTag,
             "BODY_CONTRACT protocol=1 display=%dx%d audio=%dHz/%dch yaw=[%d,%d] pitch=[%d,%d] speed=[%d,%d] tolerance=%d",
             kDisplayWidth, kDisplayHeight, kAudioSampleRateHz, kAudioChannels,
             kSafeYawMinTenths, kSafeYawMaxTenths, kSafePitchMinTenths, kSafePitchMaxTenths,
             kMinMotionSpeed, kMaxMotionSpeed, kPositionToleranceTenths);
    ESP_LOGI(kLogTag,
             "BODY_POLICY preserve_zero=%d release_torque=%d display_driver=off input_path=off output_path=off network=off",
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

    const bool passed = run_probe();
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
