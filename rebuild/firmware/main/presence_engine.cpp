#include <atomic>
#include <cinttypes>
#include <cstdint>

#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

constexpr uint32_t kPresenceTickMs = 50;
constexpr uint32_t kPresenceHeartbeatMs = 10000;
constexpr uint32_t kPresenceMinQuietMs = 7000;
constexpr uint32_t kPresenceQuietSpanMs = 11000;
constexpr uint32_t kPresencePulseMinMs = 320;
constexpr uint32_t kPresencePulseSpanMs = 520;

std::atomic<bool> g_presence_interaction_active{false};
TaskHandle_t g_presence_task_handle = nullptr;
uint32_t g_presence_sequence = 0;

uint32_t presence_mix(uint64_t value)
{
    uint32_t x = static_cast<uint32_t>(value ^ (value >> 32));
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

uint64_t presence_next_quiet_deadline(uint64_t now_ms, uint32_t sequence)
{
    const uint32_t mixed = presence_mix(now_ms + (static_cast<uint64_t>(sequence) * 0x9E3779B9ULL));
    return now_ms + kPresenceMinQuietMs + (mixed % kPresenceQuietSpanMs);
}

uint64_t presence_pulse_deadline(uint64_t now_ms, uint32_t sequence)
{
    const uint32_t mixed = presence_mix((now_ms << 1) ^ (static_cast<uint64_t>(sequence) * 0x85EBCA6BULL));
    return now_ms + kPresencePulseMinMs + (mixed % kPresencePulseSpanMs);
}

void presence_interaction_begin()
{
    g_presence_interaction_active.store(true, std::memory_order_relaxed);
}

void presence_interaction_end()
{
    g_presence_interaction_active.store(false, std::memory_order_relaxed);
}

bool presence_user_attention_active()
{
    return g_presentation_touch.down || g_touch_attention_until_ms != 0;
}

void presence_task(void*)
{
    uint64_t now_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
    uint64_t next_presence_ms = presence_next_quiet_deadline(now_ms, g_presence_sequence);
    uint64_t pulse_until_ms = 0;
    uint64_t next_heartbeat_ms = now_ms;
    bool pulse_active = false;

    while (true) {
        now_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        const bool interaction = g_presence_interaction_active.load(std::memory_order_relaxed);
        const bool user_attention = presence_user_attention_active();
        const PresentationState state = presentation_requested_state();

        if (pulse_active) {
            if (interaction || user_attention || state != PresentationState::Attentive) {
                pulse_active = false;
                pulse_until_ms = 0;
                next_presence_ms = presence_next_quiet_deadline(now_ms, ++g_presence_sequence);
            } else if (now_ms >= pulse_until_ms) {
                presentation_set_state(PresentationState::Idle, "presence-complete");
                pulse_active = false;
                pulse_until_ms = 0;
                next_presence_ms = presence_next_quiet_deadline(now_ms, ++g_presence_sequence);
            }
        } else if (!interaction &&
                   !user_attention &&
                   state == PresentationState::Idle &&
                   now_ms >= next_presence_ms) {
            presentation_set_state(PresentationState::Attentive, "presence-local");
            pulse_active = true;
            pulse_until_ms = presence_pulse_deadline(now_ms, g_presence_sequence);
        }

        if (interaction || user_attention || state != PresentationState::Idle) {
            if (!pulse_active && now_ms >= next_presence_ms) {
                next_presence_ms = presence_next_quiet_deadline(now_ms, ++g_presence_sequence);
            }
        }

        if (now_ms >= next_heartbeat_ms) {
            ESP_LOGI(kLogTag,
                     "PRESENCE_HEARTBEAT seq=%" PRIu32 " local=ready interaction=%d",
                     g_presence_sequence,
                     interaction ? 1 : 0);
            next_heartbeat_ms = now_ms + kPresenceHeartbeatMs;
        }

        vTaskDelay(pdMS_TO_TICKS(kPresenceTickMs));
    }
}

bool presence_start()
{
    if (g_presence_task_handle != nullptr) return true;

    g_presence_interaction_active.store(false, std::memory_order_relaxed);
    g_presence_sequence = 0;

    const BaseType_t created = xTaskCreate(
        presence_task,
        "kadence-presence",
        4096,
        nullptr,
        3,
        &g_presence_task_handle);
    if (created != pdPASS) {
        g_presence_task_handle = nullptr;
        ESP_LOGE(kLogTag, "PRESENCE status=failed stage=task-create");
        return false;
    }

    ESP_LOGI(kLogTag, "PRESENCE status=ready local=1 independent=1");
    return true;
}

}  // namespace
