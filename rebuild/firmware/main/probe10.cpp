#ifdef app_main
#define KADE_PROBE10_EMBEDDED 1
#undef app_main
#endif

#define KADE_PROBE9_NO_APP_MAIN 1
#include "probe9_rearm.cpp"
#undef KADE_PROBE9_NO_APP_MAIN

namespace {

constexpr int kP10OffsetTenths = 80;
constexpr int kP10RampStepTenths = 10;
constexpr int kP10RampPeriodMs = 20;
constexpr int kP10SettlePollMs = 50;
constexpr int kP10MoveTimeoutMs = 4500;
constexpr int kP10ReturnTimeoutMs = 7000;
constexpr int kP10HoldMs = 300;

static_assert(kade_body_contract::kPreserveStoredZeroCalibration);
static_assert(kade_body_contract::kReleaseTorqueAfterMotion);
static_assert(kP10OffsetTenths > 0);
static_assert(kP10OffsetTenths <=
              (kade_body_contract::kSafePitchMaxTenths -
               kade_body_contract::kSafePitchMinTenths));

bool p10_load_zero_read_only(const char* key, int* zero_position)
{
    if (key == nullptr || zero_position == nullptr) return false;

    const esp_err_t init_err = nvs_flash_init();
    if (init_err != ESP_OK) return false;

    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open("servo", NVS_READONLY, &handle);
    if (err != ESP_OK) return false;

    int32_t stored_zero = -1;
    err = nvs_get_i32(handle, key, &stored_zero);
    nvs_close(handle);
    if (err != ESP_OK || stored_zero < kP9RawPositionMin ||
        stored_zero > kP9RawPositionMax) {
        return false;
    }

    *zero_position = static_cast<int>(stored_zero);
    return true;
}

int p10_raw_to_angle(int raw_position, int zero_position)
{
    return (raw_position - zero_position) * 50 / 16;
}

bool p10_angle_to_raw(int angle_tenths, int zero_position, int* raw_position)
{
    if (raw_position == nullptr) return false;
    if (angle_tenths < kade_body_contract::kSafePitchMinTenths ||
        angle_tenths > kade_body_contract::kSafePitchMaxTenths) {
        return false;
    }

    const int mapped = zero_position + angle_tenths * 16 / 50;
    if (mapped < kP9RawPositionMin || mapped > kP9RawPositionMax) return false;
    *raw_position = mapped;
    return true;
}

bool p10_choose_target(int start_angle, int* target_angle)
{
    if (target_angle == nullptr) return false;

    const int positive = start_angle + kP10OffsetTenths;
    if (positive <= kade_body_contract::kSafePitchMaxTenths) {
        *target_angle = positive;
        return true;
    }

    const int negative = start_angle - kP10OffsetTenths;
    if (negative >= kade_body_contract::kSafePitchMinTenths) {
        *target_angle = negative;
        return true;
    }
    return false;
}

bool p10_enable_active_torque()
{
    return p9_write_byte(kP9SecondaryId, kP9RegTorqueEnable, 1);
}

bool p10_write_position(int raw_position)
{
    if (raw_position < kP9RawPositionMin || raw_position > kP9RawPositionMax) {
        return false;
    }

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
        kP9SecondaryId,
        kP9InstructionWrite,
        kP9RegGoalPosition,
        data,
        sizeof(data),
        true);
}

bool p10_read_moving(bool* moving)
{
    if (moving == nullptr) return false;
    uint8_t value = 0;
    if (!p9_read_register(kP9SecondaryId, kP9RegMoving, &value, 1)) return false;
    *moving = value != 0;
    return true;
}

bool p10_ramp(int from_angle, int to_angle, int zero_position)
{
    int current = from_angle;
    while (current != to_angle) {
        const int delta = to_angle - current;
        if (delta > kP10RampStepTenths) {
            current += kP10RampStepTenths;
        } else if (delta < -kP10RampStepTenths) {
            current -= kP10RampStepTenths;
        } else {
            current = to_angle;
        }

        int raw_position = 0;
        if (!p10_angle_to_raw(current, zero_position, &raw_position) ||
            !p10_write_position(raw_position)) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(kP10RampPeriodMs));
    }
    return true;
}

bool p10_wait_settled(int target_angle,
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
        if (!p9_read_position(kP9SecondaryId, &raw_position) ||
            !p10_read_moving(&moving)) {
            return false;
        }

        const int angle = p10_raw_to_angle(raw_position, zero_position);
        if (angle < kade_body_contract::kSafePitchMinTenths -
                        kade_body_contract::kPositionToleranceTenths ||
            angle > kade_body_contract::kSafePitchMaxTenths +
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

        vTaskDelay(pdMS_TO_TICKS(kP10SettlePollMs));
    }
    return false;
}

bool p10_verify_torque_released()
{
    uint8_t primary = 0xFF;
    uint8_t secondary = 0xFF;
    if (!p9_read_register(kP9PrimaryId, kP9RegTorqueEnable, &primary, 1) ||
        !p9_read_register(kP9SecondaryId, kP9RegTorqueEnable, &secondary, 1)) {
        return false;
    }
    return primary == 0 && secondary == 0;
}

void p10_fail_closed(const char* stage)
{
    ESP_LOGE(kLogTag, "PROBE10 status=failed stage=%s", stage);
    if (g_probe9.uart_ready) p9_release_torque();
    if (g_probe9.power_control_ready && g_probe9.power_enabled) {
        p9_set_power(false);
    }
}

bool run_probe10()
{
    ESP_LOGI(kLogTag, "PROBE10 phase=baseline");
    if (!p9_run_integrated_gate_rearm()) {
        ESP_LOGE(kLogTag, "PROBE10 status=failed stage=baseline");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE10 phase=integration");
    if (!p9_release_torque()) {
        p10_fail_closed("preflight-release");
        return false;
    }

    int primary_zero_before = 0;
    int active_zero_before = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &primary_zero_before) ||
        !p10_load_zero_read_only("zero_pos_2", &active_zero_before)) {
        p10_fail_closed("read-only-state");
        return false;
    }

    int start_raw = 0;
    if (!p9_read_position(kP9SecondaryId, &start_raw)) {
        p10_fail_closed("position-read");
        return false;
    }

    const int start_angle = p10_raw_to_angle(start_raw, active_zero_before);
    if (start_angle < kade_body_contract::kSafePitchMinTenths ||
        start_angle > kade_body_contract::kSafePitchMaxTenths) {
        p10_fail_closed("position-envelope");
        return false;
    }

    int target_angle = 0;
    int target_raw = 0;
    if (!p10_choose_target(start_angle, &target_angle) ||
        !p10_angle_to_raw(target_angle, active_zero_before, &target_raw)) {
        p10_fail_closed("target-envelope");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE10 status=ready preserve_zero=1 release_torque=1 start=%d target=%d",
             start_angle,
             target_angle);
    vTaskDelay(pdMS_TO_TICKS(500));

    if (!p10_enable_active_torque()) {
        p10_fail_closed("execute-enable");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE10 phase=execute-a");
    if (!p10_ramp(start_angle, target_angle, active_zero_before)) {
        p10_fail_closed("execute-a-command");
        return false;
    }

    int reached_angle = 0;
    if (!p10_wait_settled(
            target_angle, active_zero_before, kP10MoveTimeoutMs, &reached_angle)) {
        p10_fail_closed("execute-a-settle");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP10HoldMs));

    ESP_LOGI(kLogTag, "PROBE10 phase=execute-b");
    if (!p10_ramp(target_angle, start_angle, active_zero_before)) {
        p10_fail_closed("execute-b-command");
        return false;
    }

    int final_angle = 0;
    if (!p10_wait_settled(
            start_angle, active_zero_before, kP10ReturnTimeoutMs, &final_angle)) {
        p10_fail_closed("execute-b-settle");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        p10_fail_closed("final-release");
        return false;
    }

    int primary_zero_after = 0;
    int active_zero_after = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &primary_zero_after) ||
        !p10_load_zero_read_only("zero_pos_2", &active_zero_after) ||
        primary_zero_before != primary_zero_after ||
        active_zero_before != active_zero_after) {
        p10_fail_closed("zero-verify");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE10 phase=verify");
    if (!probe8_touch_health("health-d") || !probe8_draw_frame(true)) {
        p10_fail_closed("verify-health");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE10 status=complete first_error=%d return_error=%d torque=released preserve_zero=1 zero_unchanged=1 one_shot=1",
             p9_abs(reached_angle - target_angle),
             p9_abs(final_angle - start_angle));
    return true;
}

}  // namespace

#ifndef KADE_PROBE10_EMBEDDED
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

    const bool passed = run_probe10();

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
#endif
