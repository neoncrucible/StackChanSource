#include "body_contract.h"

#include <cinttypes>
#include <cstdio>

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

const char* reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
        case ESP_RST_POWERON:
            return "power-on";
        case ESP_RST_EXT:
            return "external-reset";
        case ESP_RST_SW:
            return "software-reset";
        case ESP_RST_PANIC:
            return "panic";
        case ESP_RST_INT_WDT:
            return "interrupt-watchdog";
        case ESP_RST_TASK_WDT:
            return "task-watchdog";
        case ESP_RST_WDT:
            return "other-watchdog";
        case ESP_RST_DEEPSLEEP:
            return "deep-sleep";
        case ESP_RST_BROWNOUT:
            return "brownout";
        case ESP_RST_SDIO:
            return "sdio";
        case ESP_RST_UNKNOWN:
        default:
            return "unknown-or-other";
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
                  mac[0],
                  mac[1],
                  mac[2],
                  mac[3],
                  mac[4],
                  mac[5]);
}

void log_contract()
{
    using namespace kade_body_contract;

    ESP_LOGI(kLogTag,
             "BODY_CONTRACT protocol=1 display=%dx%d audio=%dHz/%dch yaw=[%d,%d] pitch=[%d,%d] speed=[%d,%d] tolerance=%d",
             kDisplayWidth,
             kDisplayHeight,
             kAudioSampleRateHz,
             kAudioChannels,
             kSafeYawMinTenths,
             kSafeYawMaxTenths,
             kSafePitchMinTenths,
             kSafePitchMaxTenths,
             kMinMotionSpeed,
             kMaxMotionSpeed,
             kPositionToleranceTenths);

    ESP_LOGI(kLogTag,
             "BODY_POLICY preserve_zero=%d release_torque=%d motion_driver=off audio_driver=off display_driver=off network=off",
             kPreserveStoredZeroCalibration ? 1 : 0,
             kReleaseTorqueAfterMotion ? 1 : 0);
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));

    const esp_app_desc_t* app = esp_app_get_description();
    const esp_reset_reason_t reset_reason = esp_reset_reason();

    ESP_LOGI(kLogTag,
             "BODY_BOOT firmware=%s device_id=%s reset=%s",
             app != nullptr ? app->version : "unknown",
             device_id,
             reset_reason_name(reset_reason));

    log_contract();

    uint32_t sequence = 0;
    while (true) {
        const uint64_t uptime_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        const uint32_t free_heap = esp_get_free_heap_size();

        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%" PRIu32 " uptime_ms=%" PRIu64 " free_heap=%" PRIu32,
                 sequence++,
                 uptime_ms,
                 free_heap);

        vTaskDelay(pdMS_TO_TICKS(kHeartbeatMs));
    }
}
