#include "../firmware/main/front_touch.h"
#include "../firmware/main/listening_cue.h"
#include <array>
#include <cassert>
#include <cstdio>

int main() {
    kadence_touch::FrontTouch touch;
    assert(!touch.update(true,100));
    assert(!touch.update(false,110)); // Ten-ms spike is not a tap.
    assert(!touch.update(false,200));
    assert(!touch.update(true,300));
    assert(touch.update(true,320));
    for(uint64_t t=330;t<3000;t+=10) assert(!touch.update(true,t));
    assert(!touch.update(false,3000));
    assert(!touch.update(true,3030)); // Release bounce cannot cancel the turn.
    assert(!touch.update(true,3100));
    assert(!touch.update(false,3200));
    assert(!touch.update(false,3270));
    assert(!touch.pressed());
    assert(!touch.update(true,3350));
    assert(touch.update(true,3370)); // A second deliberate press can cancel.
    assert(!touch.update(false,3390));
    assert(!touch.update(false,3460));
    assert(!touch.update(true,3480));
    assert(!touch.update(true,3550)); // One physical double-tap is not two commands.
    assert(!touch.update(false,3700));
    assert(!touch.update(false,3770));
    assert(!touch.update(true,4000));
    assert(touch.update(true,4020));

    std::array<int16_t,kadence_cue::Samples+2> audio{};
    audio.front()=12345; audio.back()=-12345;
    kadence_cue::render(audio.data()+1);
    assert(audio.front()==12345 && audio.back()==-12345);
    assert(audio[1]==0 && audio[kadence_cue::Samples]==0);
    int crossings[2]{};
    for(size_t i=1;i<kadence_cue::Samples;++i) {
        assert(std::abs(static_cast<int>(audio[i+1]))<=2100);
        if(i>=1440 && i<1600) assert(audio[i+1]==0);
        else if(audio[i]<=0 && audio[i+1]>0) ++crossings[i<1440?0:1];
    }
    assert(crossings[0]>=58 && crossings[0]<=61);
    assert(crossings[1]>=97 && crossings[1]<=100);
    std::puts("INPUT_FEEDBACK PASS press=1 hold=1 bounce=1 rearm=1 cue_bounds=1 cue_envelope=1");
}
