#include <atomic>
#include <cstddef>
#include <cstdio>
#include <cstring>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

namespace {

using VoiceLaneEmitFn = void (*)(const char* ack);

struct VoiceLaneMessage {
    char raw[kP16FrameBytes]{};
};

enum class VoiceLaneRouteResult : uint8_t {
    NotVoice = 0,
    Consumed,
    Rejected,
};

QueueHandle_t g_voice_lane_queue = nullptr;
VoiceLaneEmitFn g_voice_lane_emit = nullptr;
std::atomic<bool> g_voice_lane_busy{false};

bool voice_lane_make_cancel_ack(const char* request_id,
                                bool active,
                                bool torque_released,
                                char* output,
                                std::size_t output_size)
{
    if (request_id == nullptr || request_id[0] == '\0' || output == nullptr || output_size == 0) {
        return false;
    }

    cJSON* root = cJSON_CreateObject();
    cJSON* payload = cJSON_CreateObject();
    if (root == nullptr || payload == nullptr) {
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    bool built = true;
    built = built && cJSON_AddNumberToObject(root, "v", 1) != nullptr;
    built = built && cJSON_AddStringToObject(root, "id", request_id) != nullptr;
    built = built && cJSON_AddStringToObject(root, "ts", "device") != nullptr;
    built = built && cJSON_AddStringToObject(root, "kind", "ack") != nullptr;
    built = built && cJSON_AddStringToObject(root, "name", "voice.cancel") != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "ok", true) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "active", active) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "cancelled", active) != nullptr;
    built = built && cJSON_AddBoolToObject(payload, "torque_released", torque_released) != nullptr;
    if (built) {
        cJSON_AddItemToObject(root, "payload", payload);
        payload = nullptr;
    }

    char* rendered = built ? cJSON_PrintUnformatted(root) : nullptr;
    if (rendered == nullptr || std::strlen(rendered) >= output_size) {
        cJSON_free(rendered);
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return false;
    }

    std::snprintf(output, output_size, "%s", rendered);
    cJSON_free(rendered);
    cJSON_Delete(root);
    return true;
}

void voice_lane_worker(void*)
{
    VoiceLaneMessage message{};
    while (true) {
        if (xQueueReceive(g_voice_lane_queue, &message, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        char ack[kP16FrameBytes]{};
        const VoiceLanCommandResult result =
            voice_lan_execute_command(message.raw, ack, sizeof(ack));
        voice_cancel_finish();

        if (result == VoiceLanCommandResult::Accepted && g_voice_lane_emit != nullptr) {
            g_voice_lane_emit(ack);
        } else {
            p9_release_torque();
            presentation_set_state(PresentationState::Idle, "voice-worker-rejected");
            presence_interaction_end();
            ESP_LOGE(kLogTag, "VOICE_LANE status=rejected torque=released");
        }

        g_voice_lane_busy.store(false);
        ESP_LOGI(kLogTag, "VOICE_LANE status=idle cancellable=1");
    }
}

bool voice_lane_start(VoiceLaneEmitFn emit)
{
    if (emit == nullptr) return false;
    if (g_voice_lane_queue != nullptr) return true;

    g_voice_lane_emit = emit;
    g_voice_lane_queue = xQueueCreate(1, sizeof(VoiceLaneMessage));
    if (g_voice_lane_queue == nullptr) return false;

    const BaseType_t created = xTaskCreate(
        voice_lane_worker,
        "kade-voice-lane",
        32768,
        nullptr,
        5,
        nullptr);
    if (created != pdPASS) {
        vQueueDelete(g_voice_lane_queue);
        g_voice_lane_queue = nullptr;
        g_voice_lane_emit = nullptr;
        return false;
    }
    return true;
}

VoiceLaneRouteResult voice_lane_route_command(const char* raw)
{
    if (raw == nullptr) return VoiceLaneRouteResult::NotVoice;

    cJSON* root = cJSON_Parse(raw);
    if (root == nullptr || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return VoiceLaneRouteResult::NotVoice;
    }

    const cJSON* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name) || name->valuestring == nullptr) {
        cJSON_Delete(root);
        return VoiceLaneRouteResult::NotVoice;
    }

    if (std::strcmp(name->valuestring, "voice.turn") == 0) {
        const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
        const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
        const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
        const bool envelope_ok =
            cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
            cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
            request_id->valuestring[0] != '\0' &&
            cJSON_IsString(kind) && kind->valuestring != nullptr &&
            std::strcmp(kind->valuestring, "command") == 0;
        cJSON_Delete(root);
        if (!envelope_ok || g_voice_lane_queue == nullptr) {
            return VoiceLaneRouteResult::Rejected;
        }

        bool expected = false;
        if (!g_voice_lane_busy.compare_exchange_strong(expected, true)) {
            ESP_LOGW(kLogTag, "VOICE_LANE status=busy rejected=voice.turn");
            return VoiceLaneRouteResult::Rejected;
        }

        VoiceLaneMessage message{};
        if (std::strlen(raw) >= sizeof(message.raw)) {
            g_voice_lane_busy.store(false);
            return VoiceLaneRouteResult::Rejected;
        }
        std::snprintf(message.raw, sizeof(message.raw), "%s", raw);
        voice_cancel_begin();
        if (xQueueSend(g_voice_lane_queue, &message, 0) != pdTRUE) {
            g_voice_lane_busy.store(false);
            return VoiceLaneRouteResult::Rejected;
        }

        ESP_LOGI(kLogTag, "VOICE_LANE status=accepted async=1 cancellable=1");
        return VoiceLaneRouteResult::Consumed;
    }

    if (std::strcmp(name->valuestring, "voice.cancel") == 0) {
        const cJSON* version = cJSON_GetObjectItemCaseSensitive(root, "v");
        const cJSON* request_id = cJSON_GetObjectItemCaseSensitive(root, "id");
        const cJSON* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
        const bool envelope_ok =
            cJSON_IsNumber(version) && version->valuedouble == 1.0 &&
            cJSON_IsString(request_id) && request_id->valuestring != nullptr &&
            request_id->valuestring[0] != '\0' && std::strlen(request_id->valuestring) < 48 &&
            cJSON_IsString(kind) && kind->valuestring != nullptr &&
            std::strcmp(kind->valuestring, "command") == 0;
        if (!envelope_ok) {
            cJSON_Delete(root);
            return VoiceLaneRouteResult::Rejected;
        }

        char request_id_copy[48]{};
        std::snprintf(request_id_copy, sizeof(request_id_copy), "%s", request_id->valuestring);
        cJSON_Delete(root);

        const bool active = g_voice_lane_busy.load();
        if (active) voice_cancel_request();
        const bool torque_released = p9_release_torque() && p10_verify_torque_released();

        char ack[kP16FrameBytes]{};
        if (!voice_lane_make_cancel_ack(
                request_id_copy, active, torque_released, ack, sizeof(ack)) ||
            g_voice_lane_emit == nullptr) {
            return VoiceLaneRouteResult::Rejected;
        }
        g_voice_lane_emit(ack);
        ESP_LOGI(kLogTag,
                 "VOICE_LANE cancel=ack active=%d torque=%s",
                 active ? 1 : 0,
                 torque_released ? "released" : "failed");
        return VoiceLaneRouteResult::Consumed;
    }

    cJSON_Delete(root);
    return VoiceLaneRouteResult::NotVoice;
}

}  // namespace
