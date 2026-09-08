#include "listening_cue.h"

namespace {
bool voice_listening_cue()
{
    if (voice_cancel_is_requested()) return false;
    if (g_user_mute.load() || g_user_volume.load() == 0) return true;
    // Called by the existing exclusive media worker, before opening the mic.
    // Uses exactly the same volume ceiling, DMA staging and hardware close.
    static std::array<int16_t,kadence_cue::Samples> samples{};
    kadence_cue::render(samples.data());
    if (!voice_lan_buffered_open_output()) return false;
    if (voice_lan_buffered_write(g_audio.output_dev,samples.data(),sizeof(samples)) != ESP_OK) {
        voice_playback_buffer_reset();
        return false;
    }
    return voice_lan_buffered_close_output(false);
}
}
