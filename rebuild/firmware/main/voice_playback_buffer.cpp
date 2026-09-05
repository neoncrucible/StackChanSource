#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "esp_heap_caps.h"

namespace {

constexpr std::size_t kVoicePlaybackPsramBytes = 4U * 1024U * 1024U;
constexpr std::size_t kVoicePlaybackDrainChunk = 8192;
constexpr int kVoicePlaybackDrainGuardMs = 120;

uint8_t* g_voice_playback_psram = nullptr;
std::size_t g_voice_playback_length = 0;
bool g_voice_playback_buffering = false;

void voice_playback_buffer_reset()
{
    if (g_voice_playback_psram != nullptr) {
        heap_caps_free(g_voice_playback_psram);
        g_voice_playback_psram = nullptr;
    }
    g_voice_playback_length = 0;
    g_voice_playback_buffering = false;
}

bool voice_lan_buffered_open_output()
{
    voice_playback_buffer_reset();
    g_voice_playback_psram = static_cast<uint8_t*>(heap_caps_malloc(
        kVoicePlaybackPsramBytes,
        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (g_voice_playback_psram == nullptr) {
        ESP_LOGE(kLogTag,
                 "VOICE_PLAYBACK status=failed stage=psram-alloc requested=%u free=%u",
                 static_cast<unsigned>(kVoicePlaybackPsramBytes),
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
        return false;
    }

    g_voice_playback_length = 0;
    g_voice_playback_buffering = true;
    ESP_LOGI(kLogTag,
             "VOICE_PLAYBACK buffer=ready capacity=%u psram_free=%u",
             static_cast<unsigned>(kVoicePlaybackPsramBytes),
             static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM)));
    return true;
}

esp_err_t voice_lan_buffered_set_out_mute(esp_codec_dev_handle_t dev, bool mute)
{
    if (g_voice_playback_buffering && !mute) return ESP_OK;
    return static_cast<esp_err_t>(esp_codec_dev_set_out_mute(dev, mute));
}

esp_err_t voice_lan_buffered_write(esp_codec_dev_handle_t dev, void* data, int len)
{
    if (!g_voice_playback_buffering) {
        return static_cast<esp_err_t>(esp_codec_dev_write(dev, data, len));
    }
    if (data == nullptr || len <= 0) return ESP_ERR_INVALID_ARG;

    const std::size_t bytes = static_cast<std::size_t>(len);
    if (g_voice_playback_psram == nullptr ||
        g_voice_playback_length + bytes > kVoicePlaybackPsramBytes) {
        ESP_LOGE(kLogTag,
                 "VOICE_PLAYBACK status=failed stage=buffer-range used=%u incoming=%u",
                 static_cast<unsigned>(g_voice_playback_length),
                 static_cast<unsigned>(bytes));
        return ESP_ERR_NO_MEM;
    }

    std::memcpy(g_voice_playback_psram + g_voice_playback_length, data, bytes);
    g_voice_playback_length += bytes;
    return ESP_OK;
}

bool voice_lan_buffered_close_output()
{
    if (!g_voice_playback_buffering || g_voice_playback_psram == nullptr ||
        g_voice_playback_length == 0) {
        voice_playback_buffer_reset();
        ESP_LOGE(kLogTag, "VOICE_PLAYBACK status=failed stage=empty-buffer");
        return false;
    }

    const uint8_t* audio = g_voice_playback_psram;
    const std::size_t audio_bytes = g_voice_playback_length;
    g_voice_playback_buffering = false;

    if (!open_output()) {
        ESP_LOGE(kLogTag, "VOICE_PLAYBACK status=failed stage=hardware-open");
        voice_playback_buffer_reset();
        return false;
    }

    bool ok = true;
    const esp_err_t unmute_err = static_cast<esp_err_t>(
        esp_codec_dev_set_out_mute(g_audio.output_dev, false));
    if (unmute_err != ESP_OK) {
        ESP_LOGE(kLogTag,
                 "VOICE_PLAYBACK status=failed stage=hardware-unmute err=%s",
                 esp_err_to_name(unmute_err));
        ok = false;
    }

    std::size_t offset = 0;
    while (ok && offset < audio_bytes) {
        const std::size_t chunk =
            std::min(kVoicePlaybackDrainChunk, audio_bytes - offset);
        const esp_err_t write_err = static_cast<esp_err_t>(esp_codec_dev_write(
            g_audio.output_dev,
            const_cast<uint8_t*>(audio + offset),
            static_cast<int>(chunk)));
        if (write_err != ESP_OK) {
            ESP_LOGE(kLogTag,
                     "VOICE_PLAYBACK status=failed stage=hardware-write err=%s offset=%u",
                     esp_err_to_name(write_err),
                     static_cast<unsigned>(offset));
            ok = false;
            break;
        }
        offset += chunk;
    }

    if (ok) {
        vTaskDelay(pdMS_TO_TICKS(kVoicePlaybackDrainGuardMs));
    }

    if (!close_output()) ok = false;

    ESP_LOGI(kLogTag,
             "VOICE_PLAYBACK status=%s buffered=1 bytes=%u network_during_playback=0",
             ok ? "complete" : "failed",
             static_cast<unsigned>(audio_bytes));
    voice_playback_buffer_reset();
    return ok;
}

}  // namespace
