#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace kadence_cue {
constexpr unsigned SampleRate = 16000;
constexpr std::size_t Samples = 3200; // 200 ms, followed by the normal DAC drain.
inline void render(int16_t* output) {
    // A soft ascending two-note terminal cue. Original synthesis, no asset or
    // network dependency; gain/mute is applied by the existing playback owner.
    constexpr float Tau = 6.28318530718f;
    for (std::size_t i = 0; i < Samples; ++i) {
        const unsigned local = i < 1440 ? i : i - 1600;
        if (i >= 1440 && i < 1600) { output[i] = 0; continue; }
        const unsigned length = i < 1440 ? 1440 : 1600;
        const float envelope = std::min({1.0f, local / 160.0f, (length - 1 - local) / 240.0f});
        const float frequency = i < 1440 ? 660.0f : 990.0f;
        output[i] = static_cast<int16_t>(2100 * envelope * std::sin(Tau * frequency * local / SampleRate));
    }
}
}
