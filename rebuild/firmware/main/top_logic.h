#pragma once
#include <algorithm>
#include <array>
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

enum class Phase { Off, Show, Input, Won, Lost };
struct Memory {
    std::array<uint8_t,24> sequence{};
    Phase phase=Phase::Off;
    int length=0, cursor=0, score=0, best=0, lit=-1;
    uint64_t epoch=0, deadline=0;
    uint32_t random=1;
    uint8_t next() { random^=random<<13; random^=random>>17; random^=random<<5; return random%3; }
    void start(uint64_t now, uint32_t seed) { random=seed?seed:1; score=0; length=1; sequence[0]=next(); show(now); }
    void show(uint64_t now) { phase=Phase::Show; cursor=0; epoch=now+600; lit=-1; deadline=now+120000; }
    void stop() { phase=Phase::Off; lit=-1; }
    void tick(uint64_t now) {
        if (phase==Phase::Show && now>=epoch) {
            const int step=static_cast<int>((now-epoch)/750);
            if (step>=length) { phase=Phase::Input; cursor=0; lit=-1; deadline=now+20000; }
            else lit=(now-epoch)%750<500?sequence[step]:-1;
        } else if (phase==Phase::Input && now>=deadline) { phase=Phase::Lost; lit=-1; deadline=now+2500; }
        else if ((phase==Phase::Lost || phase==Phase::Won) && now>=deadline) stop();
    }
    bool tap(int zone, uint64_t now) {
        if (phase!=Phase::Input || zone<0 || zone>2) return false;
        lit=zone;
        if (zone!=sequence[cursor]) { phase=Phase::Lost; deadline=now+2500; return false; }
        if (++cursor==length) {
            score=length; best=std::max(best,score);
            if (length==24) { phase=Phase::Won; deadline=now+4000; }
            else { sequence[length++]=next(); show(now); }
        } else deadline=now+20000;
        return true;
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
