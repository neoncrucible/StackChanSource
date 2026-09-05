#define app_main app_main_probe16_original
#include "probe16.cpp"
#undef app_main

#include "presentation.cpp"

#include <cstdio>
#include <cstring>

#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"

namespace {

constexpr size_t kP19LineBytes = kP16FrameBytes;

void p19_protocol_task(void*)
{
    char line[kP19LineBytes]{};
    while (true) {
        if (std::fgets(line, sizeof(line), stdin) == nullptr) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        size_t len = std::strlen(line);
        while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r')) {
            line[--len] = '\0';
        }
        if (len == 0) {
            continue;
        }

        ESP_LOGI(kLogTag, "PROBE19 phase=rx bytes=%u", static_cast<unsigned>(len));
        presentation_set_state(PresentationState::Attentive, "body-command");

        char ack[kP16FrameBytes]{};
        if (!p16_execute_pose_command(line, ack, sizeof(ack))) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "body-rejected");
            ESP_LOGE(kLogTag, "PROBE19 status=rejected torque=released");
            continue;
        }

        std::printf("%s\n", ack);
        std::fflush(stdout);
        presentation_set_state(PresentationState::Idle, "body-complete");
        ESP_LOGI(kLogTag, "PROBE19 status=ack-sent executed=1 torque=released");
    }
}

bool run_probe19()
{
    ESP_LOGI(kLogTag, "PROBE19 phase=baseline");
    if (!run_probe16()) {
        ESP_LOGE(kLogTag, "PROBE19 status=failed stage=baseline");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "PROBE19 status=failed stage=pre-transport-release");
        return false;
    }

    usb_serial_jtag_driver_config_t usb_cfg = {
        .tx_buffer_size = 1024,
        .rx_buffer_size = 1024,
    };
    const esp_err_t usb_err = usb_serial_jtag_driver_install(&usb_cfg);
    if (usb_err != ESP_OK && usb_err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(kLogTag,
                 "PROBE19 status=failed stage=usb-driver-install err=%s",
                 esp_err_to_name(usb_err));
        return false;
    }
    usb_serial_jtag_vfs_use_driver();

    const BaseType_t created = xTaskCreate(
        p19_protocol_task,
        "kade-p19-rx",
        4096,
        nullptr,
        5,
        nullptr);
    if (created != pdPASS) {
        ESP_LOGE(kLogTag, "PROBE19 status=failed stage=rx-task");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE19 status=ready transport=usb-serial-jtag primary=1 bidirectional=1 blocking_rx=1 torque=released");
    return true;
}

}  // namespace

extern "C" void app_main(void)
{
    char device_id[32]{};
    make_device_id(device_id, sizeof(device_id));
    const esp_app_desc_t* app = esp_app_get_description();
    ESP_LOGI(kLogTag,
             "BODY_BOOT device=%s fw=%s idf=%s reset=%d heap=%u",
             device_id,
             app != nullptr ? app->version : "unknown",
             esp_get_idf_version(),
             static_cast<int>(esp_reset_reason()),
             static_cast<unsigned>(esp_get_free_heap_size()));

    const bool ok = run_probe19();
    const bool presentation_ok = presentation_start(ok);
    if (!presentation_ok) {
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=start");
    }

    uint32_t heartbeat_seq = 0;
    const int64_t heartbeat_epoch_us = esp_timer_get_time();
    while (true) {
        const int64_t uptime_ms = (esp_timer_get_time() - heartbeat_epoch_us) / 1000;
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%u uptime_ms=%lld free_heap=%u status=%s presentation=%s",
                 static_cast<unsigned>(heartbeat_seq++),
                 static_cast<long long>(uptime_ms),
                 static_cast<unsigned>(esp_get_free_heap_size()),
                 ok ? "ok" : "failed",
                 presentation_ok ? "ready" : "failed");
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
