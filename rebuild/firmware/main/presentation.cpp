#include <algorithm>
#include <array>
#include <atomic>
#include <cinttypes>
#include <cstdint>
#include <cstring>
#include "esp_heap_caps.h"
#include "avatar_scene.h"
#include "top_controls.h"
#include "front_touch.h"

#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

using PresentationState = kadence_scene::State;

constexpr uint32_t kPresentationTickMs = 10;
constexpr int kTouchReadTimeoutMs = 15;
constexpr uint32_t kPresentationFrameMs = 50;
constexpr uint32_t kPresentationHeartbeatMs = 5000;
constexpr uint32_t kBootPresentationMs = 1400;
constexpr uint32_t kTouchAttentionMs = 1400;
constexpr uint16_t kUiBlack = 0x0000;

std::atomic<uint8_t> g_presentation_requested{
    static_cast<uint8_t>(PresentationState::Booting)};
std::atomic<uint32_t> g_presentation_touch_action_seq{0};
TaskHandle_t g_presentation_task_handle = nullptr;
TaskHandle_t g_presentation_input_task_handle = nullptr;
kadence_touch::FrontTouch g_front_touch;
std::atomic<uint64_t> g_presentation_capture_end_ms{0};
std::atomic<bool> g_presentation_auto_attention{false};
uint64_t g_presentation_boot_ms = 0;
uint64_t g_touch_attention_until_ms = 0;
std::atomic<bool> g_presentation_attention_active{false};
std::atomic<bool> g_presentation_touch_down{false};
std::atomic<uint32_t> g_presentation_audio_level{0};

struct PresentationTouch {
    bool down = false;
    int x = -1;
    int y = -1;
    uint64_t pressed_ms = 0;
    uint64_t last_error_ms = 0;
};

PresentationTouch g_presentation_touch;

const char* presentation_state_name(PresentationState state)
{
    switch (state) {
        case PresentationState::Booting: return "booting";
        case PresentationState::Idle: return "idle";
        case PresentationState::Attentive: return "attentive";
        case PresentationState::Listening: return "listening";
        case PresentationState::Thinking: return "thinking";
        case PresentationState::Speaking: return "speaking";
        case PresentationState::ToolWorking: return "tool-working";
        case PresentationState::Offline: return "offline";
        case PresentationState::Degraded: return "degraded";
        case PresentationState::Fault: return "fault";
        case PresentationState::Recovery: return "recovery";
        default: return "unknown";
    }
}

PresentationState presentation_requested_state()
{
    return static_cast<PresentationState>(g_presentation_requested.load(std::memory_order_relaxed));
}

uint32_t presentation_touch_action_sequence()
{
    return g_presentation_touch_action_seq.load(std::memory_order_acquire);
}

void presentation_set_state(PresentationState target, const char* reason)
{
    g_presentation_auto_attention.store(false);
    const uint8_t next = static_cast<uint8_t>(target);
    const auto previous = static_cast<PresentationState>(
        g_presentation_requested.exchange(next, std::memory_order_relaxed));
    if (previous == target) return;

    ESP_LOGI(kLogTag,
             "PRESENTATION_STATE from=%s to=%s reason=%s",
             presentation_state_name(previous),
             presentation_state_name(target),
             reason != nullptr ? reason : "unspecified");
}

bool presentation_fill_rect(int x, int y, int width, int height, uint16_t colour)
{
    if (!g_probe8_surface.panel_ready || g_probe8_surface.panel == nullptr) return false;
    if (width <= 0 || height <= 0) return true;

    const int x0 = std::clamp(x, 0, kade_body_contract::kDisplayWidth);
    const int y0 = std::clamp(y, 0, kade_body_contract::kDisplayHeight);
    const int x1 = std::clamp(x + width, 0, kade_body_contract::kDisplayWidth);
    const int y1 = std::clamp(y + height, 0, kade_body_contract::kDisplayHeight);
    if (x0 >= x1 || y0 >= y1) return true;

    static std::array<uint16_t, kade_body_contract::kDisplayWidth> scanline{};
    const uint16_t wire_colour=static_cast<uint16_t>((colour>>8)|(colour<<8));
    std::fill_n(scanline.begin(), x1 - x0, wire_colour);
    for (int row = y0; row < y1; ++row) {
        const esp_err_t err = probe8_sync_draw_bitmap(
            g_probe8_surface.panel,
            x0,
            row,
            x1,
            row + 1,
            scanline.data());
        if (err != ESP_OK) {
            ESP_LOGE(kLogTag,
                     "PRESENTATION draw_error err=%s x=%d y=%d w=%d h=%d",
                     esp_err_to_name(err), x0, row, x1 - x0, y1 - y0);
            return false;
        }
    }
    return true;
}

bool presentation_draw_shell()
{
    return presentation_fill_rect(0, 0, 320, 240, kUiBlack);
}

bool presentation_render_basic(PresentationState state, uint32_t frame)
{
    // Allocation-failure fallback keeps the same single-signal identity.
    if (!presentation_fill_rect(20, 70, 280, 120, kUiBlack)) return false;
    if (!presentation_fill_rect(28, 119, 264, 2, 0x67F0)) return false;
    const int cursor = 30 + static_cast<int>((frame * 7) % 256);
    if (!presentation_fill_rect(cursor, 115, 2, 10, 0xC7F8)) return false;
    const int height = state == PresentationState::Listening || state == PresentationState::Speaking
        ? 4 + static_cast<int>(g_presentation_audio_level.load() / 20) : 4;
    return presentation_fill_rect(158, 120 - height / 2, 4, height, 0x67F0);
}

void presentation_capture_begin(uint32_t duration_ms)
{
    g_presentation_audio_level.store(0);
    g_presentation_capture_end_ms.store(static_cast<uint64_t>(esp_timer_get_time()) / 1000 + duration_ms);
    presentation_set_state(PresentationState::Listening, "microphone-open");
}

void presentation_capture_end(bool closed)
{
    g_presentation_capture_end_ms.store(0);
    g_presentation_audio_level.store(0);
    presentation_set_state(closed ? PresentationState::Thinking : PresentationState::Degraded,
                           closed ? "microphone-closed" : "microphone-close-failed");
}

void presentation_audio_samples(const int16_t* samples, size_t count)
{
    if (samples == nullptr || count == 0) return;
    uint32_t total = 0, used = 0;
    for (size_t i = 0; i < count; i += 8) {
        const int value = samples[i];
        total += static_cast<uint32_t>(value < 0 ? -value : value);
        ++used;
    }
    g_presentation_audio_level.store(std::min<uint32_t>(1000, total / used / 4), std::memory_order_relaxed);
}

bool presentation_render(PresentationState state, uint32_t frame)
{
    // The canvas stays in PSRAM. Only the internal 8-row scratch reaches DMA.
    // The existing synchronous panel boundary completes each transfer before reuse.
    static bool attempted = false;
    static bool transfer_failed = false;
    static uint16_t* pixels = nullptr;
    static kadence_scene::Animation animation;
    alignas(4) static std::array<uint8_t, kadence_scene::Width * 8 * 2> scratch{};
    if (transfer_failed) return false; // Do not reuse memory after an unconfirmed DMA completion.
    if (!attempted) {
        attempted = true;
        pixels = static_cast<uint16_t*>(heap_caps_malloc(
            kadence_scene::Width * kadence_scene::Height * sizeof(uint16_t),
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
        if (pixels == nullptr) ESP_LOGW(kLogTag, "PRESENTATION fallback=basic reason=canvas-memory");
    }
    if (pixels == nullptr) return presentation_render_basic(state, frame);
    const uint64_t now = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
    float level = static_cast<float>(g_presentation_audio_level.load(std::memory_order_relaxed)) / 1000;
    if (state != PresentationState::Listening && state != PresentationState::Speaking) level = 0;
    const uint64_t end = g_presentation_capture_end_ms.load();
    const uint32_t remaining = end > now ? static_cast<uint32_t>(end - now) : 0;
    animation.render(pixels, state, now, level, remaining);
    top_controls_overlay(pixels, now);
    for (int row = 0; row < kadence_scene::Height; row += 8) {
        kadence_scene::encode_rgb565(pixels + row * kadence_scene::Width,
                                    scratch.data(), kadence_scene::Width * 8);
        if (probe8_sync_draw_bitmap(g_probe8_surface.panel, 0, row,
                kadence_scene::Width, row + 8, scratch.data()) != ESP_OK) {
            transfer_failed = true;
            return false;
        }
    }
    return true;
}

void presentation_poll_touch(uint64_t now_ms)
{
    if (!g_probe8_surface.touch_ready || g_probe8_surface.touch == nullptr) return;

    const uint8_t start_register = 0x02;
    uint8_t data[6]{};
    const esp_err_t err = i2c_master_transmit_receive(
        g_probe8_surface.touch,
        &start_register,
        1,
        data,
        sizeof(data),
        kTouchReadTimeoutMs);

    if (err != ESP_OK) {
        if (g_presentation_touch.last_error_ms == 0 ||
            now_ms - g_presentation_touch.last_error_ms >= 1000) {
            ESP_LOGW(kLogTag,
                     "PRESENTATION_TOUCH status=read-error err=%s",
                     esp_err_to_name(err));
            g_presentation_touch.last_error_ms = now_ms;
        }
        return;
    }

    const int points = data[0] & 0x0F;
    const bool down = points > 0;
    const int x = ((data[1] & 0x0F) << 8) | data[2];
    const int y = ((data[3] & 0x0F) << 8) | data[4];

    if (points > 2) return; // Ignore malformed controller samples.
    const bool action = g_front_touch.update(down, now_ms);
    g_presentation_touch.down = g_front_touch.pressed();
    g_presentation_touch_down.store(g_presentation_touch.down, std::memory_order_release);
    if (!action) return;
    g_presentation_touch.x = x;
    g_presentation_touch.y = y;
    const uint32_t sequence = g_presentation_touch_action_seq.fetch_add(1, std::memory_order_release) + 1;
    ESP_LOGI(kLogTag, "PRESENTATION_TOUCH type=press action=voice-toggle seq=%lu x=%d y=%d",
             static_cast<unsigned long>(sequence), x, y);
    const auto current = presentation_requested_state();
    if (current == PresentationState::Idle || current == PresentationState::Offline || current == PresentationState::Degraded) {
        presentation_set_state(PresentationState::Attentive, "touch-press");
        g_presentation_auto_attention.store(true);
    }
    g_touch_attention_until_ms = now_ms + kTouchAttentionMs;
    g_presentation_attention_active.store(true, std::memory_order_release);
}

void presentation_input_task(void*)
{
    while (true) {
        const uint64_t now = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        presentation_poll_touch(now);
        top_controls_tick(now);
        if (presentation_requested_state() == PresentationState::Booting && now - g_presentation_boot_ms >= kBootPresentationMs)
            presentation_set_state(PresentationState::Idle, "boot-complete");
        if (!g_presentation_touch.down && g_touch_attention_until_ms && now >= g_touch_attention_until_ms) {
            g_touch_attention_until_ms = 0;
            g_presentation_attention_active.store(false, std::memory_order_release);
            if (g_presentation_auto_attention.exchange(false) && presentation_requested_state() == PresentationState::Attentive)
                presentation_set_state(PresentationState::Idle, "attention-complete");
        }
        vTaskDelay(pdMS_TO_TICKS(kPresentationTickMs));
    }
}

void presentation_task(void*)
{
    uint32_t frame = 0;
    uint64_t next_frame_ms = 0;
    uint64_t next_heartbeat_ms = 0;
    PresentationState last_rendered = PresentationState::Recovery;

    while (true) {
        const uint64_t now_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
        const PresentationState requested = presentation_requested_state();

        if (requested != last_rendered || now_ms >= next_frame_ms) {
            if (!presentation_render(requested, frame++)) {
                ESP_LOGE(kLogTag, "PRESENTATION status=render-failed");
                vTaskDelay(pdMS_TO_TICKS(250));
                continue;
            }
            last_rendered = requested;
            next_frame_ms = now_ms + kPresentationFrameMs;
        }

        if (now_ms >= next_heartbeat_ms) {
            ESP_LOGI(kLogTag,
                     "PRESENTATION_HEARTBEAT state=%s frame=%" PRIu32 " touch=%s",
                     presentation_state_name(requested),
                     frame,
                     g_probe8_surface.touch_ready ? "ready" : "unavailable");
            next_heartbeat_ms = now_ms + kPresentationHeartbeatMs;
        }

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

bool presentation_start(bool runtime_ok)
{
    if (!g_probe8_surface.panel_ready || g_probe8_surface.panel == nullptr) {
        ESP_LOGE(kLogTag, "PRESENTATION status=unavailable reason=panel-not-ready");
        return false;
    }
    if (g_presentation_task_handle != nullptr) return true;

    g_presentation_boot_ms = static_cast<uint64_t>(esp_timer_get_time()) / 1000ULL;
    g_touch_attention_until_ms = 0;
    g_presentation_touch_action_seq.store(0, std::memory_order_release);
    g_presentation_requested.store(
        static_cast<uint8_t>(runtime_ok ? PresentationState::Booting : PresentationState::Fault),
        std::memory_order_relaxed);

    if (!presentation_draw_shell()) {
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=shell");
        return false;
    }
    if (!presentation_render(presentation_requested_state(), 0)) {
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=initial-frame");
        return false;
    }
    if (!probe8_set_backlight(62)) {
        ESP_LOGW(kLogTag, "PRESENTATION backlight=status-degraded");
    }

    if (xTaskCreate(presentation_input_task, "kadence-input", 8192, nullptr, 5,
                    &g_presentation_input_task_handle) != pdPASS) return false;

    const BaseType_t created = xTaskCreate(
        presentation_task,
        "kadence-ui",
        6144,
        nullptr,
        3,
        &g_presentation_task_handle);
    if (created != pdPASS) {
        g_presentation_task_handle = nullptr;
        ESP_LOGE(kLogTag, "PRESENTATION status=failed stage=task-create");
        return false;
    }

    ESP_LOGI(kLogTag,
             "PRESENTATION status=ready state=%s renderer=local touch=%s frame_ms=%" PRIu32,
             presentation_state_name(presentation_requested_state()),
             g_probe8_surface.touch_ready ? "ready" : "unavailable",
             kPresentationFrameMs);
    return true;
}

}  // namespace
