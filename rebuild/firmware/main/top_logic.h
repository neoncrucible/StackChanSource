#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace kadence_top {
enum class Gesture { None, Forward, Backward, Hold, Tap0, Tap1, Tap2 };
struct Touch {
    bool down=false, acted=false;
    int start=0, zone=0;
    uint64_t since=0;
    Gesture update(uint8_t value, uint64_t now) {
        const int a=value&3, b=(value>>2)&3, c=(value>>4)&3;
        const int total=a+b+c;
        if (!total) {
            const bool tap=down && !acted && now-since>=60 && now-since<900;
            down=false; acted=false;
            return tap ? static_cast<Gesture>(static_cast<int>(Gesture::Tap0)+zone) : Gesture::None;
        }
        const int position=100*(c-a)/total;
        if (!down) { down=true; acted=false; start=position; since=now; zone=a>=b&&a>=c?0:b>=c?1:2; }
        if (!acted && position-start>=65) { acted=true; return Gesture::Forward; }
        if (!acted && position-start<=-65) { acted=true; return Gesture::Backward; }
        if (!acted && now-since>=1200) { acted=true; return Gesture::Hold; }
        return Gesture::None;
    }
};

// Q15 gain slews over ~16 ms. The codec remains at its proven maximum of 55;
// level 100 exactly preserves accepted playback amplitude, with no amplification.
inline void apply_gain(int16_t* samples, size_t count, int volume, bool mute, int& gain) {
    const int target=mute?0:std::clamp(volume,0,100)*32768/100;
    for (size_t i=0;i<count;++i) {
        gain += std::clamp(target-gain,-128,128);
        samples[i]=static_cast<int16_t>(static_cast<int32_t>(samples[i])*gain/32768);
    }
}
}
