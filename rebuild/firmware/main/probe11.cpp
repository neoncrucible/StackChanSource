#define app_main app_main_probe10_original
#include "probe10.cpp"
#undef app_main

#include <cstdio>
#include <cstring>

#include "cJSON.h"

namespace {

constexpr int kP11OffsetTenths = 60;
constexpr int kP11RampStepTenths = 10;
constexpr int kP11RampPeriodMs = 20;
constexpr int kP11SettlePollMs = 50;
constexpr int kP11MoveTimeoutMs = 5000;
constexpr int kP11ReturnTimeoutMs = 7000;
constexpr int kP11HoldMs = 300;

static_assert(kade_body_contract::kPreserveStoredZeroCalibration);
static_assert(kade_body_contract::kReleaseTorqueAfterMotion);
static_assert(kP11OffsetTenths > 0);

struct P11Pose {
    int yaw = 0;
    int pitch = 0;
};

int p11_step_toward(int current, int target)
{
    const int delta = target - current;
    if (delta > kP11RampStepTenths) return current + kP11RampStepTenths;
    if (delta < -kP11RampStepTenths) return current - kP11RampStepTenths;
    return target;
}

bool p11_decode_pose(const char* raw, P11Pose* output)
{
    if (raw == nullptr || output == nullptr) return false;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* yaw = payload != nullptr
        ? cJSON_GetObjectItemCaseSensitive(payload, "yaw")
        : nullptr;
    const cJSON* pitch = payload != nullptr
        ? cJSON_GetObjectItemCaseSensitive(payload, "pitch")
        : nullptr;

    const bool valid =
        cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
        cJSON_IsString(kind) && kind->valuestring != nullptr &&
        std::strcmp(kind->valuestring, "command") == 0 &&
        cJSON_IsString(name) && name->valuestring != nullptr &&
        std::strcmp(name->valuestring, "body.pose") == 0 &&
        cJSON_IsObject(payload) &&
        cJSON_IsNumber(yaw) && yaw->valuedouble == static_cast<double>(yaw->valueint) &&
        cJSON_IsNumber(pitch) && pitch->valuedouble == static_cast<double>(pitch->valueint);

    if (!valid) {
        cJSON_Delete(root);
        return false;
    }

    const auto safe = kade_body_contract::clamp_motion(
        yaw->valueint,
        pitch->valueint,
        kade_body_contract::kDefaultMotionSpeed);
    output->yaw = safe.yaw;
    output->pitch = safe.pitch;
    cJSON_Delete(root);
    return true;
}

bool p11_protocol_self_test()
{
    P11Pose pose{};
    if (!p11_decode_pose(
            "{\"v\":1,\"id\":\"a\",\"ts\":\"x\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":120,\"pitch\":420}}",
            &pose) ||
        pose.yaw != 120 || pose.pitch != 420) {
        return false;
    }

    if (!p11_decode_pose(
            "{\"v\":1,\"id\":\"b\",\"ts\":\"x\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":9999,\"pitch\":-9999}}",
            &pose) ||
        pose.yaw != kade_body_contract::kSafeYawMaxTenths ||
        pose.pitch != kade_body_contract::kSafePitchMinTenths) {
        return false;
    }

    if (p11_decode_pose(
            "{\"v\":1,\"id\":\"c\",\"ts\":\"x\",\"kind\":\"command\",\"name\":\"body.unknown\",\"payload\":{\"yaw\":0,\"pitch\":400}}",
            &pose)) {
        return false;
    }
    if (p11_decode_pose(
            "{\"v\":2,\"id\":\"d\",\"ts\":\"x\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":0,\"pitch\":400}}",
            &pose)) {
        return false;
    }
    if (p11_decode_pose("not-json", &pose)) return false;

    return true;
}

bool p11_choose_target(int start, int minimum, int maximum, int* target)
{
    if (target == nullptr) return false;
    const int positive = start + kP11OffsetTenths;
    if (positive <= maximum) {
        *target = positive;
        return true;
    }
    const int negative = start - kP11OffsetTenths;
    if (negative >= minimum) {
        *target = negative;
        return true;
    }
    return false;
}

bool p11_ramp_dual(const P11Pose& from,
                   const P11Pose& to,
                   int yaw_zero,
                   int pitch_zero)
{
    P11Pose current = from;
    while (current.yaw != to.yaw || current.pitch != to.pitch) {
        current.yaw = p11_step_toward(current.yaw, to.yaw);
        current.pitch = p11_step_toward(current.pitch, to.pitch);

        int yaw_raw = 0;
        int pitch_raw = 0;
        if (!p9_angle_to_raw(current.yaw, yaw_zero, &yaw_raw) ||
            !p10_angle_to_raw(current.pitch, pitch_zero, &pitch_raw) ||
            !p9_write_position(yaw_raw) ||
            !p10_write_position(pitch_raw)) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(kP11RampPeriodMs));
    }
    return true;
}

bool p11_wait_dual(const P11Pose& target,
                   int yaw_zero,
                   int pitch_zero,
                   int timeout_ms,
                   P11Pose* final_pose)
{
    const int64_t deadline_us = esp_timer_get_time() +
                                static_cast<int64_t>(timeout_ms) * 1000;
    int stable_samples = 0;

    while (esp_timer_get_time() < deadline_us) {
        int yaw_raw = 0;
        int pitch_raw = 0;
        bool yaw_moving = true;
        bool pitch_moving = true;
        if (!p9_read_position(kP9PrimaryId, &yaw_raw) ||
            !p9_read_position(kP9SecondaryId, &pitch_raw) ||
            !p9_read_moving(&yaw_moving) ||
            !p10_read_moving(&pitch_moving)) {
            return false;
        }

        const P11Pose current{
            .yaw = p9_raw_to_angle(yaw_raw, yaw_zero),
            .pitch = p10_raw_to_angle(pitch_raw, pitch_zero),
        };
        if (current.yaw < kade_body_contract::kSafeYawMinTenths -
                              kade_body_contract::kPositionToleranceTenths ||
            current.yaw > kade_body_contract::kSafeYawMaxTenths +
                              kade_body_contract::kPositionToleranceTenths ||
            current.pitch < kade_body_contract::kSafePitchMinTenths -
                                kade_body_contract::kPositionToleranceTenths ||
            current.pitch > kade_body_contract::kSafePitchMaxTenths +
                                kade_body_contract::kPositionToleranceTenths) {
            return false;
        }

        if (!yaw_moving && !pitch_moving &&
            p9_abs(current.yaw - target.yaw) <=
                kade_body_contract::kPositionToleranceTenths &&
            p9_abs(current.pitch - target.pitch) <=
                kade_body_contract::kPositionToleranceTenths) {
            ++stable_samples;
            if (stable_samples >= 2) {
                if (final_pose != nullptr) *final_pose = current;
                return true;
            }
        } else {
            stable_samples = 0;
        }
        vTaskDelay(pdMS_TO_TICKS(kP11SettlePollMs));
    }
    return false;
}

void p11_fail_closed(const char* stage)
{
    ESP_LOGE(kLogTag, "PROBE11 status=failed stage=%s", stage);
    if (g_probe9.uart_ready) p9_release_torque();
    if (g_probe9.power_control_ready && g_probe9.power_enabled) {
        p9_set_power(false);
    }
}

bool run_probe11()
{
    ESP_LOGI(kLogTag, "PROBE11 phase=baseline");
    if (!run_probe10()) {
        ESP_LOGE(kLogTag, "PROBE11 status=failed stage=baseline");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE11 phase=contract");
    if (!p11_protocol_self_test()) {
        p11_fail_closed("contract-self-test");
        return false;
    }
    ESP_LOGI(kLogTag, "PROBE11 contract status=ready version=1 bounded=1 reject_unknown=1");

    int yaw_zero_before = 0;
    int pitch_zero_before = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &yaw_zero_before) ||
        !p10_load_zero_read_only("zero_pos_2", &pitch_zero_before)) {
        p11_fail_closed("read-only-state");
        return false;
    }

    int yaw_raw = 0;
    int pitch_raw = 0;
    if (!p9_read_position(kP9PrimaryId, &yaw_raw) ||
        !p9_read_position(kP9SecondaryId, &pitch_raw)) {
        p11_fail_closed("position-read");
        return false;
    }

    const P11Pose start{
        .yaw = p9_raw_to_angle(yaw_raw, yaw_zero_before),
        .pitch = p10_raw_to_angle(pitch_raw, pitch_zero_before),
    };
    if (start.yaw < kade_body_contract::kSafeYawMinTenths ||
        start.yaw > kade_body_contract::kSafeYawMaxTenths ||
        start.pitch < kade_body_contract::kSafePitchMinTenths ||
        start.pitch > kade_body_contract::kSafePitchMaxTenths) {
        p11_fail_closed("position-envelope");
        return false;
    }

    P11Pose requested{};
    if (!p11_choose_target(
            start.yaw,
            kade_body_contract::kSafeYawMinTenths,
            kade_body_contract::kSafeYawMaxTenths,
            &requested.yaw) ||
        !p11_choose_target(
            start.pitch,
            kade_body_contract::kSafePitchMinTenths,
            kade_body_contract::kSafePitchMaxTenths,
            &requested.pitch)) {
        p11_fail_closed("target-envelope");
        return false;
    }

    char command_json[256]{};
    const int command_length = std::snprintf(
        command_json,
        sizeof(command_json),
        "{\"v\":1,\"id\":\"probe11\",\"ts\":\"bounded\",\"kind\":\"command\",\"name\":\"body.pose\",\"payload\":{\"yaw\":%d,\"pitch\":%d}}",
        requested.yaw,
        requested.pitch);
    if (command_length <= 0 ||
        command_length >= static_cast<int>(sizeof(command_json))) {
        p11_fail_closed("command-frame");
        return false;
    }

    P11Pose target{};
    if (!p11_decode_pose(command_json, &target) ||
        target.yaw != requested.yaw || target.pitch != requested.pitch) {
        p11_fail_closed("command-decode");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE11 status=ready preserve_zero=1 release_torque=1 start_yaw=%d start_pitch=%d target_yaw=%d target_pitch=%d",
             start.yaw,
             start.pitch,
             target.yaw,
             target.pitch);
    vTaskDelay(pdMS_TO_TICKS(400));

    if (!p9_enable_primary_torque() || !p10_enable_active_torque()) {
        p11_fail_closed("execute-enable");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE11 phase=execute-a");
    if (!p11_ramp_dual(start, target, yaw_zero_before, pitch_zero_before)) {
        p11_fail_closed("execute-a-command");
        return false;
    }

    P11Pose reached{};
    if (!p11_wait_dual(
            target,
            yaw_zero_before,
            pitch_zero_before,
            kP11MoveTimeoutMs,
            &reached)) {
        p11_fail_closed("execute-a-settle");
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(kP11HoldMs));

    ESP_LOGI(kLogTag, "PROBE11 phase=execute-b");
    if (!p11_ramp_dual(target, start, yaw_zero_before, pitch_zero_before)) {
        p11_fail_closed("execute-b-command");
        return false;
    }

    P11Pose returned{};
    if (!p11_wait_dual(
            start,
            yaw_zero_before,
            pitch_zero_before,
            kP11ReturnTimeoutMs,
            &returned)) {
        p11_fail_closed("execute-b-settle");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        p11_fail_closed("final-release");
        return false;
    }

    int yaw_zero_after = 0;
    int pitch_zero_after = 0;
    if (!p10_load_zero_read_only("zero_pos_1", &yaw_zero_after) ||
        !p10_load_zero_read_only("zero_pos_2", &pitch_zero_after) ||
        yaw_zero_before != yaw_zero_after || pitch_zero_before != pitch_zero_after) {
        p11_fail_closed("zero-verify");
        return false;
    }

    ESP_LOGI(kLogTag, "PROBE11 phase=verify");
    if (!probe8_touch_health("health-e")) {
        p11_fail_closed("verify-health");
        return false;
    }
    if (!p9_prepare_verify_transition() || !open_input()) {
        p11_fail_closed("verify-transition");
        return false;
    }
    if (!sample_input("post-command")) {
        close_input();
        p11_fail_closed("verify-sample");
        return false;
    }
    if (!close_input() || !probe8_draw_frame(true)) {
        p11_fail_closed("verify-close");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE11 status=complete yaw_error=%d pitch_error=%d yaw_return=%d pitch_return=%d torque=released preserve_zero=1 zero_unchanged=1 command_contract=ready post_health=ok one_shot=1",
             p9_abs(reached.yaw - target.yaw),
             p9_abs(reached.pitch - target.pitch),
             p9_abs(returned.yaw - start.yaw),
             p9_abs(returned.pitch - start.pitch));
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

    const bool passed = run_probe11();

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
