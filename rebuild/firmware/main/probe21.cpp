#define app_main app_main_probe20_embedded
#include "probe20.cpp"
#undef app_main

#include "voice_lan.cpp"

namespace {

constexpr size_t kP21LineBytes = kP16FrameBytes;

void p21_protocol_task(void*)
{
    char line[kP21LineBytes]{};
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
        if (len == 0) continue;

        ESP_LOGI(kLogTag, "PROBE21 phase=rx bytes=%u", static_cast<unsigned>(len));

        char ack[kP16FrameBytes]{};
        const VoiceLanCommandResult voice_result =
            voice_lan_execute_command(line, ack, sizeof(ack));
        if (voice_result == VoiceLanCommandResult::Accepted) {
            std::printf("%s\n", ack);
            std::fflush(stdout);
            ESP_LOGI(kLogTag, "PROBE21 voice-turn=ack-sent correlated=1");
            continue;
        }
        if (voice_result == VoiceLanCommandResult::Rejected) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "voice-turn-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "PROBE21 voice-turn=rejected torque=released");
            continue;
        }

        const DeviceAudioCommandResult audio_result =
            device_audio_execute_command(line, ack, sizeof(ack));
        if (audio_result == DeviceAudioCommandResult::Accepted) {
            std::printf("%s\n", ack);
            std::fflush(stdout);
            ESP_LOGI(kLogTag, "PROBE21 device-audio=ack-sent correlated=1");
            continue;
        }
        if (audio_result == DeviceAudioCommandResult::Rejected) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "device-audio-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "PROBE21 device-audio=rejected torque=released");
            continue;
        }

        const P20PresentationResult presentation_result =
            p20_execute_presentation_command(line, ack, sizeof(ack));
        if (presentation_result == P20PresentationResult::Accepted) {
            std::printf("%s\n", ack);
            std::fflush(stdout);
            ESP_LOGI(kLogTag, "PROBE21 presentation=ack-sent correlated=1");
            continue;
        }
        if (presentation_result == P20PresentationResult::Rejected) {
            ESP_LOGE(kLogTag, "PROBE21 presentation=rejected");
            continue;
        }

        presence_interaction_begin();
        presentation_set_state(PresentationState::Attentive, "body-command");

        if (!p16_execute_pose_command(line, ack, sizeof(ack))) {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "body-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "PROBE21 status=rejected torque=released");
            continue;
        }

        std::printf("%s\n", ack);
        std::fflush(stdout);
        presentation_set_state(PresentationState::Idle, "body-complete");
        presence_interaction_end();
        ESP_LOGI(kLogTag, "PROBE21 status=ack-sent executed=1 torque=released");
    }
}

bool run_probe21()
{
    ESP_LOGI(kLogTag, "PROBE21 phase=baseline");

    // Do not call run_probe20(): it owns its own serial reader. Reuse the same
    // proven Probe16 baseline and the duplex audio objects inherited through
    // Probe20, then create exactly one Probe21 serial command task.
    if (!run_probe16()) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=baseline");
        return false;
    }

    if (!g_audio.ready || g_audio.input_dev == nullptr || g_audio.output_dev == nullptr) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=audio-transport");
        return false;
    }

    if (!p9_release_torque() || !p10_verify_torque_released()) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=pre-transport-release");
        return false;
    }

    usb_serial_jtag_driver_config_t usb_cfg = {
        .tx_buffer_size = 1024,
        .rx_buffer_size = 1024,
    };
    const esp_err_t usb_err = usb_serial_jtag_driver_install(&usb_cfg);
    if (usb_err != ESP_OK && usb_err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(kLogTag,
                 "PROBE21 status=failed stage=usb-driver-install err=%s",
                 esp_err_to_name(usb_err));
        return false;
    }
    usb_serial_jtag_vfs_use_driver();

    const BaseType_t created = xTaskCreate(
        p21_protocol_task,
        "kade-p21-rx",
        4096,
        nullptr,
        5,
        nullptr);
    if (created != pdPASS) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=rx-task");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE21 status=ready control=usb-serial-jtag audio=runtime-duplex voice=lan-opus-60ms handoff=1 torque=released");
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

    const bool ok = run_probe21();
    const bool presentation_ok = presentation_start(ok);
    if (!presentation_ok) {
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=start");
    }

    const bool presence_ok = presentation_ok && presence_start();
    if (!presence_ok) {
        ESP_LOGE(kLogTag, "PRESENCE status=failed stage=start");
    }

    uint32_t heartbeat_seq = 0;
    const int64_t heartbeat_epoch_us = esp_timer_get_time();
    while (true) {
        const int64_t uptime_ms = (esp_timer_get_time() - heartbeat_epoch_us) / 1000;
        ESP_LOGI(kLogTag,
                 "BODY_HEARTBEAT seq=%u uptime_ms=%lld free_heap=%u status=%s presentation=%s presence=%s audio=%s voice=lan-opus-60ms",
                 static_cast<unsigned>(heartbeat_seq++),
                 static_cast<long long>(uptime_ms),
                 static_cast<unsigned>(esp_get_free_heap_size()),
                 ok ? "ok" : "failed",
                 presentation_ok ? "ready" : "failed",
                 presence_ok ? "ready" : "failed",
                 g_audio.ready ? "ready" : "failed");
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
