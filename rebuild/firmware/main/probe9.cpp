#define KADE_PROBE8_NO_APP_MAIN 1
#include "probe8_sync.cpp"
#undef KADE_PROBE8_NO_APP_MAIN

#include <array>
#include <cstddef>
#include <cstdint>

#include "driver/uart.h"
#include "nvs.h"
#include "nvs_flash.h"

namespace {

constexpr int kP9IoTimeoutMs = 50;
constexpr int kP9WarmSettleMs = 650;
constexpr int kP9TransportSettleMs = 100;
constexpr int kP9WarmRetryDelayMs = 70;
constexpr int kP9WarmAttempts = 3;
constexpr int kP9SettlePollMs = 50;
constexpr int kP9RampPeriodMs = 20;
constexpr int kP9RampStepTenths = 10;
constexpr int kP9OffsetTenths = 100;
constexpr int kP9MoveTimeoutMs = 4500;
constexpr int kP9ReturnTimeoutMs = 7000;
constexpr int kP9HoldMs = 300;
constexpr int kP9ServoCommandTime = 20;

constexpr uart_port_t kP9ServoUart = UART_NUM_1;
constexpr int kP9ServoBaud = 1000000;
constexpr gpio_num_t kP9ServoTx = GPIO_NUM_6;
constexpr gpio_num_t kP9ServoRx = GPIO_NUM_7;
constexpr uint8_t kP9PrimaryId = 1;
constexpr uint8_t kP9SecondaryId = 2;
constexpr uint8_t kP9BroadcastId = 0xFE;

constexpr uint8_t kP9PowerExpanderAddress = 0x6F;
constexpr uint8_t kP9RegVersion = 0x02;
constexpr uint8_t kP9RegGpioModeLow = 0x03;
constexpr uint8_t kP9RegGpioOutputLow = 0x05;
constexpr uint8_t kP9RegGpioPullUpLow = 0x09;
constexpr uint8_t kP9RegGpioPullDownLow = 0x0B;
constexpr uint8_t kP9PowerPinMask = 0x01;

constexpr uint8_t kP9InstructionRead = 0x02;
constexpr uint8_t kP9InstructionWrite = 0x03;
constexpr uint8_t kP9RegTorqueEnable = 40;
constexpr uint8_t kP9RegGoalPosition = 42;
constexpr uint8_t kP9RegPresentPosition = 56;
constexpr uint8_t kP9RegMoving = 66;
constexpr int kP9RawPositionMin = 0;
constexpr int kP9RawPositionMax = 1000;

static_assert(kade_body_contract::kPreserveStoredZeroCalibration);
static_assert(kade_body_contract::kReleaseTorqueAfterMotion);
static_assert(kP9OffsetTenths > 0);
static_assert(kP9OffsetTenths <=
              (kade_body_contract::kSafeYawMaxTenths -
               kade_body_contract::kSafeYawMinTenths));

struct Probe9Runtime {
    i2c_master_dev_handle_t power_expander = nullptr;
    bool power_control_ready = false;
    bool power_enabled = false;
    bool uart_ready = false;
    bool failed = false;
};

Probe9Runtime g_probe9;

int p9_abs(int value)
{
    return value < 0 ? -value : value;
}

bool p9_i2c_read(uint8_t reg, uint8_t* value)
{
    if (g_probe9.power_expander == nullptr || value == nullptr) return false;
    return i2c_master_transmit_receive(
               g_probe9.power_expander, &reg, 1, value, 1, kI2cTimeoutMs) == ESP_OK;
}

bool p9_i2c_write(uint8_t reg, uint8_t value)
{
    if (g_probe9.power_expander == nullptr) return false;
    const uint8_t payload[2] = {reg, value};
    return i2c_master_transmit(
               g_probe9.power_expander, payload, sizeof(payload), kI2cTimeoutMs) == ESP_OK;
}

bool p9_i2c_update_bit(uint8_t reg, uint8_t mask, bool enabled)
{
    uint8_t value = 0;
    if (!p9_i2c_read(reg, &value)) return false;
    value = enabled ? static_cast<uint8_t>(value | mask)
                    : static_cast<uint8_t>(value & static_cast<uint8_t>(~mask));
    return p9_i2c_write(reg, value);
}

bool p9_initialise_power_control()
{
    if (g_control.i2c_bus == nullptr) return false;

    i2c_device_config_t config{};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = kP9PowerExpanderAddress;
    config.scl_speed_hz = 100000;

    const esp_err_t add_err = i2c_master_bus_add_device(
        g_control.i2c_bus, &config, &g_probe9.power_expander);
    if (add_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "PROBE9 status=failed stage=control-endpoint err=%s",
                 esp_err_to_name(add_err));
        return false;
    }

    uint8_t version = 0;
    if (!p9_i2c_read(kP9RegVersion, &version) || version == 0 || version == 0xFF) {
        ESP_LOGE(kLogTag, "PROBE9 status=failed stage=control-version");
        return false;
    }

    if (!p9_i2c_update_bit(kP9RegGpioModeLow, kP9PowerPinMask, true) ||
        !p9_i2c_update_bit(kP9RegGpioPullDownLow, kP9PowerPinMask, false) ||
        !p9_i2c_update_bit(kP9RegGpioPullUpLow, kP9PowerPinMask, true)) {
        ESP_LOGE(kLogTag, "PROBE9 status=failed stage=control-config");
        return false;
    }

    g_probe9.power_control_ready = true;
    ESP_LOGI(kLogTag, "PROBE9 control status=ready version=0x%02X", version);
    return true;
}

bool p9_set_power(bool enabled)
{
    if (!g_probe9.power_control_ready) return false;
    if (!p9_i2c_update_bit(kP9RegGpioOutputLow, kP9PowerPinMask, enabled)) return false;
    g_probe9.power_enabled = enabled;
    return true;
}

bool p9_initialise_uart()
{
    uart_config_t config{};
    config.baud_rate = kP9ServoBaud;
    config.data_bits = UART_DATA_8_BITS;
    config.parity = UART_PARITY_DISABLE;
    config.stop_bits = UART_STOP_BITS_1;
    config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    config.rx_flow_ctrl_thresh = 0;
    config.source_clk = UART_SCLK_DEFAULT;

    esp_err_t err = uart_driver_install(kP9ServoUart, 256, 256, 0, nullptr, 0);
    if (err != ESP_OK) return false;
    err = uart_param_config(kP9ServoUart, &config);
    if (err != ESP_OK) {
        uart_driver_delete(kP9ServoUart);
        return false;
    }
    err = uart_set_pin(
        kP9ServoUart, kP9ServoTx, kP9ServoRx, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        uart_driver_delete(kP9ServoUart);
        return false;
    }

    g_probe9.uart_ready = true;
    return true;
}

bool p9_uart_read_exact(uint8_t* data, std::size_t length, int64_t deadline_us)
{
    std::size_t offset = 0;
    while (offset < length && esp_timer_get_time() < deadline_us) {
        const int count = uart_read_bytes(
            kP9ServoUart,
            data + offset,
            static_cast<uint32_t>(length - offset),
            0);
        if (count > 0) {
            offset += static_cast<std::size_t>(count);
            continue;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    return offset == length;
}

bool p9_uart_find_header(int64_t deadline_us)
{
    uint8_t previous = 0;
    while (esp_timer_get_time() < deadline_us) {
        uint8_t current = 0;
        if (!p9_uart_read_exact(&current, 1, deadline_us)) return false;
        if (previous == 0xFF && current == 0xFF) return true;
        previous = current;
    }
    return false;
}

bool p9_read_response(uint8_t expected_id, uint8_t* payload, std::size_t payload_length)
{
    const int64_t deadline_us = esp_timer_get_time() +
                                static_cast<int64_t>(kP9IoTimeoutMs) * 1000;
    if (!p9_uart_find_header(deadline_us)) return false;

    uint8_t header[3]{};
    if (!p9_uart_read_exact(header, sizeof(header), deadline_us)) return false;
    const uint8_t response_id = header[0];
    const uint8_t length = header[1];
    const uint8_t status = header[2];
    if (response_id != expected_id || length != payload_length + 2 || status != 0) {
        return false;
    }

    std::array<uint8_t, 8> data{};
    if (payload_length > data.size()) return false;
    if (payload_length > 0 &&
        !p9_uart_read_exact(data.data(), payload_length, deadline_us)) {
        return false;
    }

    uint8_t checksum = 0;
    if (!p9_uart_read_exact(&checksum, 1, deadline_us)) return false;

    uint8_t sum = static_cast<uint8_t>(response_id + length + status);
    for (std::size_t i = 0; i < payload_length; ++i) {
        sum = static_cast<uint8_t>(sum + data[i]);
    }
    if (checksum != static_cast<uint8_t>(~sum)) return false;

    if (payload != nullptr) {
        for (std::size_t i = 0; i < payload_length; ++i) payload[i] = data[i];
    }
    return true;
}

bool p9_send_packet(uint8_t id,
                    uint8_t instruction,
                    uint8_t address,
                    const uint8_t* data,
                    std::size_t data_length,
                    bool expect_ack)
{
    if (!g_probe9.uart_ready || data_length > 8) return false;

    std::array<uint8_t, 16> packet{};
    const uint8_t protocol_length = static_cast<uint8_t>(data_length + 3);
    packet[0] = 0xFF;
    packet[1] = 0xFF;
    packet[2] = id;
    packet[3] = protocol_length;
    packet[4] = instruction;
    packet[5] = address;

    uint8_t sum = static_cast<uint8_t>(id + protocol_length + instruction + address);
    for (std::size_t i = 0; i < data_length; ++i) {
        packet[6 + i] = data[i];
        sum = static_cast<uint8_t>(sum + data[i]);
    }
    packet[6 + data_length] = static_cast<uint8_t>(~sum);
    const std::size_t packet_length = 7 + data_length;

    uart_flush_input(kP9ServoUart);
    const int written = uart_write_bytes(
        kP9ServoUart,
        reinterpret_cast<const char*>(packet.data()),
        packet_length);
    if (written != static_cast<int>(packet_length)) return false;
    if (uart_wait_tx_done(kP9ServoUart, pdMS_TO_TICKS(100)) != ESP_OK) return false;

    return !expect_ack || p9_read_response(id, nullptr, 0);
}

bool p9_write_byte(uint8_t id, uint8_t address, uint8_t value)
{
    return p9_send_packet(
        id, kP9InstructionWrite, address, &value, 1, id != kP9BroadcastId);
}

bool p9_read_register(uint8_t id,
                      uint8_t address,
                      uint8_t* output,
                      std::size_t length)
{
    if (output == nullptr || length == 0 || length > 8) return false;
    const uint8_t requested = static_cast<uint8_t>(length);
    if (!p9_send_packet(id, kP9InstructionRead, address, &requested, 1, false)) {
        return false;
    }
    return p9_read_response(id, output, length);
}

bool p9_read_position(uint8_t id, int* raw_position)
{
    if (raw_position == nullptr) return false;
    uint8_t data[2]{};
    if (!p9_read_register(id, kP9RegPresentPosition, data, sizeof(data))) return false;
    *raw_position = (static_cast<int>(data[0]) << 8) | data[1];
    return *raw_position >= kP9RawPositionMin && *raw_position <= kP9RawPositionMax;
}

bool p9_read_moving(bool* moving)
{
    if (moving == nullptr) return false;
    uint8_t value = 0;
    if (!p9_read_register(kP9PrimaryId, kP9RegMoving, &value, 1)) return false;
    *moving = value != 0;
    return true;
}

bool p9_release_torque()
{
    if (!g_probe9.uart_ready) return false;
    const bool primary_ok = p9_write_byte(kP9PrimaryId, kP9RegTorqueEnable, 0);
    const bool secondary_ok = p9_write_byte(kP9SecondaryId, kP9RegTorqueEnable, 0);
    if (!primary_ok || !secondary_ok) {
        const uint8_t disabled = 0;
        p9_send_packet(
            kP9BroadcastId,
            kP9InstructionWrite,
            kP9RegTorqueEnable,
            &disabled,
            1,
            false);
    }
    return primary_ok && secondary_ok;
}

bool p9_enable_primary_torque()
{
    return p9_write_byte(kP9PrimaryId, kP9RegTorqueEnable, 1);
}

bool p9_write_position(int raw_position)
{
    if (raw_position < kP9RawPositionMin || raw_position > kP9RawPositionMax) return false;
    const uint16_t position = static_cast<uint16_t>(raw_position);
    const uint16_t command_time = static_cast<uint16_t>(kP9ServoCommandTime);
    const uint16_t speed = 0;
    const uint8_t data[6] = {
        static_cast<uint8_t>((position >> 8) & 0xFF),
        static_cast<uint8_t>(position & 0xFF),
        static_cast<uint8_t>((command_time >> 8) & 0xFF),
        static_cast<uint8_t>(command_time & 0xFF),
        static_cast<uint8_t>((speed >> 8) & 0xFF),
        static_cast<uint8_t>(speed & 0xFF),
    };
    return p9_send_packet(
        kP9PrimaryId,
        kP9InstructionWrite,
        kP9RegGoalPosition,
        data,
        sizeof(data),
        true);
}

bool p9_warm_transport()
{
    for (int attempt = 1; attempt <= kP9WarmAttempts; ++attempt) {
        int primary = -1;
        int secondary = -1;
        const bool primary_ok = p9_read_position(kP9PrimaryId, &primary);
        const bool secondary_ok = p9_read_position(kP9SecondaryId, &secondary);
        ESP_LOGI(kLogTag,
                 "PROBE9 warm attempt=%d primary_ok=%d secondary_ok=%d",
                 attempt,
                 primary_ok ? 1 : 0,
                 secondary_ok ? 1 : 0);
        if (primary_ok && secondary_ok) return true;
        if (attempt < kP9WarmAttempts) {
            vTaskDelay(pdMS_TO_TICKS(kP9WarmRetryDelayMs));
        }
    }
    return false;
}

bool p9_load_zero_read_only(int* zero_position)
{
    if (zero_position == nullptr) return false;
    const esp_err_t init_err = nvs_flash_init();
    if (init_err != ESP_OK) return false;

    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open("servo", NVS_READONLY, &handle);
    if (err != ESP_OK) return false;

    int32_t stored_zero = -1;
    err = nvs_get_i32(handle, "zero_pos_1", &stored_zero);
    nvs_close(handle);
    if (err != ESP_OK || stored_zero < kP9RawPositionMin || stored_zero > kP9RawPositionMax) {
        return false;
    }

    *zero_position = static_cast<int>(stored_zero);
    return true;
}

int p9_raw_to_angle(int raw_position, int zero_position)
{
    return (raw_position - zero_position) * 50 / 16;
}

bool p9_angle_to_raw(int angle_tenths, int zero_position, int* raw_position)
{
    if (raw_position == nullptr) return false;
    if (angle_tenths < kade_body_contract::kSafeYawMinTenths ||
        angle_tenths > kade_body_contract::kSafeYawMaxTenths) {
        return false;
    }
    const int mapped = zero_position + angle_tenths * 16 / 50;
    if (mapped < kP9RawPositionMin || mapped > kP9RawPositionMax) return false;
    *raw_position = mapped;
    return true;
}

bool p9_choose_target(int start_angle, int* target_angle)
{
    if (target_angle == nullptr) return false;
    const int positive = start_angle + kP9OffsetTenths;
    if (positive <= kade_body_contract::kSafeYawMaxTenths) {
        *target_angle = positive;
        return true;
    }
    const int negative = start_angle - kP9OffsetTenths;
    if (negative >= kade_body_contract::kSafeYawMinTenths) {
        *target_angle = negative;
        return true;
    }
    return false;
}

bool p9_ramp(int from_angle, int to_angle, int zero_position)
{
    int current = from_angle;
    while (current != to_angle) {
        const int delta = to_angle - current;
        if (delta > kP9RampStepTenths) {
            current += kP9RampStepTenths;
        } else if (delta < -kP9RampStepTenths) {
            current -= kP9RampStepTenths;
        } else {
            current = to_angle;
        }

        int raw_position = 0;
        if (!p9_angle_to_raw(current, zero_position, &raw_position) ||
            !p9_write_position(raw_position)) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(kP9RampPeriodMs));
    }
    return true;
}

bool p9_wait_settled(int target_angle,
                     int zero_position,
                     int timeout_ms,
                     int* final_angle)
{
    const int64_t deadline_us = esp_timer_get_time() +
                                static_cast<int64_t>(timeout_ms) * 1000;
    int stable_samples = 0;

    while (esp_timer_get_time() < deadline_us) {
        int raw_position = 0;
        bool moving = true;
        if (!p9_read_position(kP9PrimaryId, &raw_position) || !p9_read_moving(&moving)) {
            return false;
        }

        const int angle = p9_raw_to_angle(raw_position, zero_position);
        if (angle < kade_body_contract::kSafeYawMinTenths -
                        kade_body_contract::kPositionToleranceTenths ||
            angle > kade_body_contract::kSafeYawMaxTenths +
                        kade_body_contract::kPositionToleranceTenths) {
            return false;
        }

        if (!moving &&
            p9_abs(angle - target_angle) <=
                kade_body_contract::kPositionToleranceTenths) {
            ++stable_samples;
            if (stable_samples >= 2) {
                if (final_angle != nullptr) *final_angle = angle;
                return true;
            }
        } else {
            stable_samples = 0;
        }
        vTaskDelay(pdMS_TO_TICKS(kP9SettlePollMs));
    }
    return false;
}

void p9_fail_closed(const char* stage)
{
    ESP_LOGE(kLogTag, "PROBE9 status=failed stage=%s", stage);
    if (g_probe9.uart_ready) p9_release_torque();
    if (g_probe9.power_control_ready && g_probe9.power_enabled) {
        p9_set_power(false);
    }
    g_probe9.failed = true;
}

bool p9_run_integrated_gate()
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
             "PROBE9 status=complete first_error=%d return_error=%d torque=released preserve_zero=1 one_shot=1",
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

    const bool passed = p9_run_integrated_gate();

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
