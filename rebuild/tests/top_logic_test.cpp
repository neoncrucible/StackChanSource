#include "../firmware/main/top_logic.h"
#include <cassert>
#include <cstdio>
#include <limits>

int main() {
    using namespace kadence_top;
    Touch touch;
    assert(touch.update(3,100)==Gesture::None);
    assert(touch.update(12,200)==Gesture::Forward);
    assert(touch.update(48,300)==Gesture::None);
    assert(touch.update(0,400)==Gesture::None);
    touch.update(48,500);
    assert(touch.update(3,600)==Gesture::Backward);
    touch.update(0,700);
    touch.update(12,800);
    assert(touch.update(12,2000)==Gesture::Hold);
    assert(touch.update(12,3300)==Gesture::None);
    assert(touch.update(0,3400)==Gesture::None);
    for (int zone=0;zone<3;++zone) {
        touch.update(3<<(2*zone),4000);
        assert(touch.update(0,4100)==static_cast<Gesture>(static_cast<int>(Gesture::Tap0)+zone));
    }
    touch.update(3,5000); assert(touch.update(0,5010)==Gesture::None);
    Memory memory; uint64_t now=0;
    memory.start(now,23);
    assert(!memory.tap(0,0));
    for (int round=1;round<=24;++round) {
        assert(memory.length==round);
        now=memory.epoch+round*750;
        memory.tick(now);
        assert(memory.phase==Phase::Input);
        for (int i=0;i<round;++i) assert(memory.tap(memory.sequence[i],++now));
        assert(memory.score==round);
    }
    assert(memory.phase==Phase::Won && memory.best==24);
    memory.tick(memory.deadline); assert(memory.phase==Phase::Off);
    memory.start(++now,91); memory.tick(memory.epoch+750);
    assert(!memory.tap((memory.sequence[0]+1)%3,++now));
    assert(memory.phase==Phase::Lost); memory.stop();
    memory.start(++now,1); memory.tick(memory.epoch+750); memory.tick(memory.deadline);
    assert(memory.phase==Phase::Lost);
    int gain=32768;
    std::array<int16_t,512> audio{}; audio.fill(32767);
    apply_gain(audio.data(),audio.size(),100,false,gain);
    for(auto sample:audio) assert(sample==32767);
    audio.fill(-32768); apply_gain(audio.data(),audio.size(),50,false,gain);
    assert(audio.back()==-16384);
    for (size_t i=1;i<audio.size();++i) assert(audio[i]>=audio[i-1]);
    audio.fill(32767); apply_gain(audio.data(),audio.size(),100,true,gain);
    assert(audio.back()==0 && gain==0);
    audio.fill(-32768); apply_gain(audio.data(),audio.size(),500,false,gain);
    assert(audio.back()==-32768 && gain==32768);
    std::puts("TOP_LOGIC PASS gestures=1 hold=1 game=1 bounded=1 gain=1 no_amplification=1");
}
