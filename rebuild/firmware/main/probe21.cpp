#define app_main app_main_probe20_embedded
#include "probe20.cpp"
#undef app_main

#include "freertos/semphr.h"

#include "voice_cancel_io.cpp"
#include "voice_playback_buffer.cpp"

// Probe21 alone stages network-delivered PCM before touching the speaker and
// wraps the LAN socket operations with a cancellation hook. The proven lower-
// level codec functions remain unchanged; these aliases exist only while
// compiling voice_lan.cpp in this translation unit.
#define connect voice_cancel_connect
#define send voice_cancel_send
#define recv voice_cancel_recv
#define close voice_cancel_close
#define open_output voice_lan_buffered_open_output
#define close_output voice_lan_buffered_close_output
#define esp_codec_dev_set_out_mute voice_lan_buffered_set_out_mute
#define esp_codec_dev_write voice_lan_buffered_write
#include "voice_lan.cpp"
#undef esp_codec_dev_write
#undef esp_codec_dev_set_out_mute
#undef close_output
#undef open_output
#undef close
#undef recv
#undef send
#undef connect

#include "voice_turn_lane.cpp"

namespace {

constexpr size_t kP21LineBytes = kP16FrameBytes;
constexpr uint32_t kP21TaskStackBytes = 32768;
SemaphoreHandle_t g_p21_tx_lock = nullptr;

void p21_emit_ack(const char* ack)
{
    if (ack == nullptr || ack[0] == '\0') return;
    if (g_p21_tx_lock != nullptr) {
        xSemaphoreTake(g_p21_tx_lock, portMAX_DELAY);
    }
    std::printf("%s\n", ack);
    std::fflush(stdout);
    if (g_p21_tx_lock != nullptr) {
        xSemaphoreGive(g_p21_tx_lock);
    }
}

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

        const VoiceLaneRouteResult voice_result = voice_lane_route_command(line);
        if (voice_result == VoiceLaneRouteResult::Consumed) {
            continue;
        }
        if (voice_result == VoiceLaneRouteResult::Rejected) {
            p9_release_torque();
            ESP_LOGE(kLogTag, "PROBE21 voice-lane=rejected torque=released");
            continue;
        }

        char ack[kP16FrameBytes]{};
        const DeviceAudioCommandResult audio_result =
            device_audio_execute_command(line, ack, sizeof(ack));
        if (audio_result == DeviceAudioCommandResult::Accepted) {
            p21_emit_ack(ack);
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
            p21_emit_ack(ack);
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

        p21_emit_ack(ack);
        presentation_set_state(PresentationState::Idle, "body-complete");
        presence_interaction_end();
        ESP_LOGI(kLogTag, "PROBE21 status=ack-sent executed=1 torque=released");
    }
}

bool run_probe21()
{
    ESP_LOGI(kLogTag, "PROBE21 phase=baseline");

    // Do not call run_probe20(): it owns its own serial reader. Reuse the same
    // proven Probe16 baseline and duplex audio objects, then keep exactly one
    // Probe21 control reader while voice work runs on its own worker lane.
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

    g_p21_tx_lock = xSemaphoreCreateMutex();
    if (g_p21_tx_lock == nullptr) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=tx-lock");
        return false;
    }

    if (!voice_lane_start(p21_emit_ack)) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=voice-worker");
        return false;
    }

    const BaseType_t created = xTaskCreate(
        p21_protocol_task,
        "kade-p21-rx",
        kP21TaskStackBytes,
        nullptr,
        5,
        nullptr);
    if (created != pdPASS) {
        ESP_LOGE(kLogTag, "PROBE21 status=failed stage=rx-task");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PROBE21 status=ready control=usb-serial-jtag audio=runtime-duplex voice=lan-opus-60ms async=1 cancellable=1 buffered-playback=psram handoff=1 torque=released");
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
                 "BODY_HEARTBEAT seq=%u uptime_ms=%lld free_heap=%u status=%s presentation=%s presence=%s audio=%s voice=lan-opus-60ms async=1 cancellable=1 buffered-playback=psram",
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
