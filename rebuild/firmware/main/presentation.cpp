#include <algorithm>
#include <array>
#include <atomic>
#include <cinttypes>
#include <cstdint>

#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {

enum class PresentationState : uint8_t {
    Booting = 0,
    Idle,
    Attentive,
    Listening,
    Thinking,
    Speaking,
    ToolWorking,
    Offline,
    Degraded,
    Fault,
    Recovery,
};

constexpr uint32_t kPresentationTickMs = 40;
constexpr uint32_t kPresentationFrameMs = 160;
constexpr uint32_t kPresentationHeartbeatMs = 5000;
constexpr uint32_t kBootPresentationMs = 1400;
constexpr uint32_t kTouchAttentionMs = 1400;
constexpr int kFaceX = 36;
constexpr int kFaceY = 52;
constexpr int kFaceW = 248;
constexpr int kFaceH = 138;

constexpr uint16_t kUiBlack = 0x0000;
constexpr uint16_t kUiShadow = 0x1082;
constexpr uint16_t kUiDim = 0x2945;
constexpr uint16_t kUiCyan = 0x07FF;
constexpr uint16_t kUiMagenta = 0xF81F;
constexpr uint16_t kUiWhite = 0xFFFF;
constexpr uint16_t kUiAmber = 0xFD20;
constexpr uint16_t kUiRed = 0xF800;

std::atomic<uint8_t> g_presentation_requested{
    static_cast<uint8_t>(PresentationState::Booting)};
TaskHandle_t g_presentation_task_handle = nullptr;
uint64_t g_presentation_boot_ms = 0;
uint64_t g_touch_attention_until_ms = 0;

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

void presentation_set_state(PresentationState target, const char* reason)
{
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
    std::fill_n(scanline.begin(), x1 - x0, colour);
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

bool presentation_draw_chamfered_eye(int x,
                                     int y,
                                     int width,
                                     int height,
                                     uint16_t colour,
                                     int pupil_shift,
                                     bool pupil)
{
    const int cut = std::max(2, height / 4);
    if (!presentation_fill_rect(x + cut, y, width - (2 * cut), height, colour)) return false;
    if (!presentation_fill_rect(x, y + cut, width, height - (2 * cut), colour)) return false;

    const int inset = 4;
    if (!presentation_fill_rect(x + cut + inset,
                                y + inset,
                                width - (2 * (cut + inset)),
                                height - (2 * inset),
                                kUiBlack)) {
        return false;
    }
    if (!presentation_fill_rect(x + inset,
                                y + cut + inset,
                                width - (2 * inset),
                                height - (2 * (cut + inset)),
                                kUiBlack)) {
        return false;
    }

    if (pupil) {
        const int pupil_size = std::max(4, height / 3);
        const int pupil_x = x + (width / 2) - (pupil_size / 2) + pupil_shift;
        const int pupil_y = y + (height / 2) - (pupil_size / 2);
        if (!presentation_fill_rect(pupil_x, pupil_y, pupil_size, pupil_size, kUiWhite)) return false;
    }
    return true;
}

bool presentation_draw_shell()
{
    if (!presentation_fill_rect(0,
                                0,
                                kade_body_contract::kDisplayWidth,
                                kade_body_contract::kDisplayHeight,
                                kUiBlack)) {
        return false;
    }

    if (!presentation_fill_rect(24, 22, 70, 2, kUiShadow)) return false;
    if (!presentation_fill_rect(226, 22, 70, 2, kUiShadow)) return false;
    if (!presentation_fill_rect(24, 216, 70, 2, kUiShadow)) return false;
    if (!presentation_fill_rect(226, 216, 70, 2, kUiShadow)) return false;

    if (!presentation_fill_rect(14, 14, 3, 18, kUiCyan)) return false;
    if (!presentation_fill_rect(303, 208, 3, 18, kUiMagenta)) return false;
    return true;
}

bool presentation_draw_fault_cross(uint16_t colour)
{
    constexpr int kStep = 8;
    for (int i = 0; i < 8; ++i) {
        if (!presentation_fill_rect(128 + (i * kStep),
                                    88 + (i * kStep),
                                    7,
                                    7,
                                    colour)) {
            return false;
        }
        if (!presentation_fill_rect(184 - (i * kStep),
                                    88 + (i * kStep),
                                    7,
                                    7,
                                    colour)) {
            return false;
        }
    }
    return true;
}

bool presentation_render(PresentationState state, uint32_t frame)
{
    if (!presentation_fill_rect(kFaceX, kFaceY, kFaceW, kFaceH, kUiBlack)) return false;

    const uint32_t slow_phase = frame / 5;
    const int gaze = static_cast<int>(slow_phase % 3) * 3 - 3;
    const bool blink = (frame % 31) == 0;
    const uint16_t pulse = ((frame / 4) % 2) == 0 ? kUiCyan : kUiWhite;

    switch (state) {
        case PresentationState::Booting: {
            const int width = 42 + static_cast<int>((frame % 12) * 12);
            const int x = (kade_body_contract::kDisplayWidth - width) / 2;
            if (!presentation_fill_rect(x, 116, width, 4, kUiCyan)) return false;
            if (!presentation_fill_rect(158, 106, 4, 24, kUiMagenta)) return false;
            break;
        }

        case PresentationState::Idle: {
            const int eye_h = blink ? 4 : 20;
            const int eye_y = 94 + ((20 - eye_h) / 2);
            if (!presentation_draw_chamfered_eye(64, eye_y, 72, eye_h, kUiCyan, gaze, !blink)) return false;
            if (!presentation_draw_chamfered_eye(184, eye_y, 72, eye_h, kUiCyan, gaze, !blink)) return false;
            if (!presentation_fill_rect(145, 158, 30, 3, kUiDim)) return false;
            if (!presentation_fill_rect(158, 174, 4, 4, ((frame / 8) % 2) ? kUiMagenta : kUiShadow)) return false;
            break;
        }

        case PresentationState::Attentive: {
            if (!presentation_draw_chamfered_eye(58, 84, 82, 34, kUiCyan, 0, true)) return false;
            if (!presentation_draw_chamfered_eye(180, 84, 82, 34, kUiCyan, 0, true)) return false;
            if (!presentation_fill_rect(136, 154, 48, 4, kUiWhite)) return false;
            if (!presentation_fill_rect(154, 166, 12, 3, kUiMagenta)) return false;
            break;
        }

        case PresentationState::Listening: {
            if (!presentation_draw_chamfered_eye(62, 88, 76, 28, pulse, -2, true)) return false;
            if (!presentation_draw_chamfered_eye(182, 88, 76, 28, pulse, 2, true)) return false;
            const int centre = 160;
            const int wave = 7 + static_cast<int>((frame % 5) * 3);
            if (!presentation_fill_rect(centre - 20, 154 - (wave / 2), 5, wave, kUiCyan)) return false;
            if (!presentation_fill_rect(centre - 3, 148 - (wave / 2), 6, wave + 12, kUiWhite)) return false;
            if (!presentation_fill_rect(centre + 15, 154 - (wave / 2), 5, wave, kUiCyan)) return false;
            break;
        }

        case PresentationState::Thinking: {
            const int shift = ((frame / 3) % 2) ? 6 : -6;
            if (!presentation_draw_chamfered_eye(66, 98, 68, 14, kUiCyan, shift, true)) return false;
            if (!presentation_draw_chamfered_eye(186, 98, 68, 14, kUiCyan, -shift, true)) return false;
            for (int i = 0; i < 3; ++i) {
                const uint16_t colour = (static_cast<int>(frame / 2) % 3) == i ? kUiWhite : kUiDim;
                if (!presentation_fill_rect(143 + (i * 14), 158, 7, 7, colour)) return false;
            }
            break;
        }

        case PresentationState::Speaking: {
            if (!presentation_draw_chamfered_eye(64, 92, 72, 22, kUiCyan, gaze, true)) return false;
            if (!presentation_draw_chamfered_eye(184, 92, 72, 22, kUiCyan, gaze, true)) return false;
            const int mouth_w = 30 + static_cast<int>((frame % 6) * 9);
            const int mouth_h = 4 + static_cast<int>((frame % 3) * 3);
            if (!presentation_fill_rect(160 - (mouth_w / 2), 153, mouth_w, mouth_h, kUiWhite)) return false;
            break;
        }

        case PresentationState::ToolWorking: {
            if (!presentation_draw_chamfered_eye(66, 98, 68, 14, kUiDim, 0, false)) return false;
            if (!presentation_draw_chamfered_eye(186, 98, 68, 14, kUiDim, 0, false)) return false;
            constexpr std::array<std::pair<int, int>, 4> points = {{{148, 148}, {166, 148}, {166, 166}, {148, 166}}};
            const int active = static_cast<int>((frame / 2) % points.size());
            for (int i = 0; i < static_cast<int>(points.size()); ++i) {
                if (!presentation_fill_rect(points[i].first,
                                            points[i].second,
                                            8,
                                            8,
                                            i == active ? kUiMagenta : kUiShadow)) {
                    return false;
                }
            }
            break;
        }

        case PresentationState::Offline: {
            if (!presentation_draw_chamfered_eye(68, 100, 64, 10, kUiDim, 0, false)) return false;
            if (!presentation_draw_chamfered_eye(188, 100, 64, 10, kUiDim, 0, false)) return false;
            if (!presentation_fill_rect(136, 158, 18, 3, kUiDim)) return false;
            if (!presentation_fill_rect(166, 158, 18, 3, kUiDim)) return false;
            break;
        }

        case PresentationState::Degraded: {
            if (!presentation_draw_chamfered_eye(64, 94, 72, 18, kUiAmber, 0, true)) return false;
            if (!presentation_draw_chamfered_eye(184, 94, 72, 18, kUiAmber, 0, true)) return false;
            if (!presentation_fill_rect(158, 146, 4, 18, kUiAmber)) return false;
            if (!presentation_fill_rect(158, 170, 4, 4, kUiAmber)) return false;
            break;
        }

        case PresentationState::Fault: {
            if (!presentation_draw_fault_cross(kUiRed)) return false;
            if (!presentation_fill_rect(132, 166, 56, 4, kUiRed)) return false;
            break;
        }

        case PresentationState::Recovery: {
            const int active = static_cast<int>((frame / 2) % 5);
            for (int i = 0; i < 5; ++i) {
                const int height = 10 + (i * 8);
                if (!presentation_fill_rect(122 + (i * 18),
                                            145 - height,
                                            8,
                                            height,
                                            i <= active ? kUiCyan : kUiShadow)) {
                    return false;
                }
            }
            if (!presentation_fill_rect(120, 158, 86, 3, kUiWhite)) return false;
            break;
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
        kI2cTimeoutMs);

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

    if (down && !g_presentation_touch.down) {
        g_presentation_touch.down = true;
        g_presentation_touch.x = x;
        g_presentation_touch.y = y;
        g_presentation_touch.pressed_ms = now_ms;
        ESP_LOGI(kLogTag, "PRESENTATION_TOUCH type=press x=%d y=%d", x, y);
        presentation_set_state(PresentationState::Attentive, "touch-press");
        g_touch_attention_until_ms = now_ms + kTouchAttentionMs;
        return;
    }

    if (down) {
        g_presentation_touch.x = x;
        g_presentation_touch.y = y;
        return;
    }

    if (g_presentation_touch.down) {
        const uint64_t held_ms = now_ms - g_presentation_touch.pressed_ms;
        ESP_LOGI(kLogTag,
                 "PRESENTATION_TOUCH type=release action=attention x=%d y=%d held_ms=%" PRIu64,
                 g_presentation_touch.x,
                 g_presentation_touch.y,
                 held_ms);
        g_presentation_touch.down = false;
        g_presentation_touch.x = -1;
        g_presentation_touch.y = -1;
        g_touch_attention_until_ms = now_ms + kTouchAttentionMs;
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
        presentation_poll_touch(now_ms);

        PresentationState requested = presentation_requested_state();
        if (requested == PresentationState::Booting &&
            now_ms - g_presentation_boot_ms >= kBootPresentationMs) {
            presentation_set_state(PresentationState::Idle, "boot-complete");
            requested = PresentationState::Idle;
        }

        if (requested == PresentationState::Attentive &&
            !g_presentation_touch.down &&
            g_touch_attention_until_ms != 0 &&
            now_ms >= g_touch_attention_until_ms) {
            g_touch_attention_until_ms = 0;
            presentation_set_state(PresentationState::Idle, "attention-complete");
            requested = PresentationState::Idle;
        }

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

        vTaskDelay(pdMS_TO_TICKS(kPresentationTickMs));
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

    const BaseType_t created = xTaskCreate(
        presentation_task,
        "kadence-ui",
        6144,
        nullptr,
        4,
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
