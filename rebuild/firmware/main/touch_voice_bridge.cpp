#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

using TouchVoiceEmitFn = void (*)(const char* line);

TouchVoiceEmitFn g_touch_voice_emit = nullptr;
TaskHandle_t g_touch_voice_task_handle = nullptr;

bool touch_voice_make_event(const char* name,
                            uint32_t sequence,
                            bool active,
                            char* output,
                            std::size_t output_size)
{
    if (name == nullptr || output == nullptr || output_size == 0) return false;

    const int written = std::snprintf(
        output,
        output_size,
        "{\"v\":1,\"id\":\"touch-%08lx\",\"ts\":\"device\",\"kind\":\"event\","
        "\"name\":\"%s\",\"payload\":{\"trigger\":\"touch\",\"seq\":%lu,\"active\":%s}}",
        static_cast<unsigned long>(sequence),
        name,
        static_cast<unsigned long>(sequence),
        active ? "true" : "false");
    return written > 0 && static_cast<std::size_t>(written) < output_size;
}

bool touch_voice_consume_host_event_ack(const char* raw)
{
    if (raw == nullptr || raw[0] != '{') return false;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return false;
    }

    const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    const cJSON* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    const cJSON* accepted = payload
        ? cJSON_GetObjectItemCaseSensitive(payload, "accepted")
        : nullptr;

    const bool consumed =
        cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
        cJSON_IsString(kind) && kind->valuestring != nullptr &&
        std::strcmp(kind->valuestring, "ack") == 0 &&
        cJSON_IsString(name) && name->valuestring != nullptr &&
        std::strcmp(name->valuestring, "host.event") == 0 &&
        cJSON_IsString(accepted) && accepted->valuestring != nullptr &&
        (std::strcmp(accepted->valuestring, "voice.request") == 0 ||
         std::strcmp(accepted->valuestring, "voice.touch-cancel") == 0);

    cJSON_Delete(root);
    if (consumed) {
        ESP_LOGI(kLogTag, "TOUCH_VOICE host-event-ack=consumed");
    }
    return consumed;
}

void touch_voice_task(void*)
{
    uint32_t seen = presentation_touch_action_sequence();

    while (true) {
        const uint32_t current = presentation_touch_action_sequence();
        if (current != seen) {
            seen = current;
            if (top_front_cancel()) continue;
            const bool active = g_voice_lane_busy.load();
            const char* event_name = active ? "voice.touch-cancel" : "voice.request";

            if (active) {
                voice_cancel_request();
                (void)p9_release_torque();
                presentation_set_state(PresentationState::Recovery, "touch-voice-cancel");
            } else {
                presentation_set_state(PresentationState::Attentive, "touch-voice-request");
            }

            char event[kP16FrameBytes]{};
            if (touch_voice_make_event(event_name, current, active, event, sizeof(event)) &&
                g_touch_voice_emit != nullptr) {
                g_touch_voice_emit(event);
                ESP_LOGI(kLogTag,
                         "TOUCH_VOICE event=%s seq=%lu active=%d",
                         event_name,
                         static_cast<unsigned long>(current),
                         active ? 1 : 0);
            } else {
                ESP_LOGE(kLogTag, "TOUCH_VOICE status=failed stage=event-emit");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(30));
    }
}

bool touch_voice_bridge_start(TouchVoiceEmitFn emit)
{
    if (emit == nullptr) return false;
    if (g_touch_voice_task_handle != nullptr) return true;

    g_touch_voice_emit = emit;
    const BaseType_t created = xTaskCreate(
        touch_voice_task,
        "kade-touch-voice",
        4096,
        nullptr,
        4,
        &g_touch_voice_task_handle);
    if (created != pdPASS) {
        g_touch_voice_task_handle = nullptr;
        g_touch_voice_emit = nullptr;
        return false;
    }

    ESP_LOGI(kLogTag, "TOUCH_VOICE status=ready trigger=release policy=idle-request-active-cancel");
    return true;
}

}  // namespace
