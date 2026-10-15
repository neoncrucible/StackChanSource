#include <cassert>
#include <cstring>
#include "../firmware/main/speech_endpoint.h"
using kadence_speech::Endpoint;

int main() {
    // A one-second question completes after 720 ms classified silence, not 4 s.
    Endpoint short_turn(8000);
    for (int i=0;i<34;++i) assert(short_turn.feed(true)==Endpoint::Reason::Listening);
    for (int i=0;i<23;++i) assert(short_turn.feed(false)==Endpoint::Reason::Listening);
    assert(short_turn.feed(false)==Endpoint::Reason::Silence);
    assert(short_turn.speech_seen());
    // A normal half-second pause inside a sentence must retain the next word.
    Endpoint pause(8000);
    for (int i=0;i<10;++i) pause.feed(true);
    for (int i=0;i<17;++i) assert(!pause.finished()), pause.feed(false);
    for (int i=0;i<10;++i) assert(pause.feed(true)==Endpoint::Reason::Listening);
    for (int i=0;i<23;++i) assert(pause.feed(false)==Endpoint::Reason::Listening);
    assert(pause.feed(false)==Endpoint::Reason::Silence);
    // Silence before speech and an isolated click cannot arm early endpointing.
    Endpoint empty(8000);
    for (int i=0;i<99;++i) assert(empty.feed(i==5)==Endpoint::Reason::Listening);
    assert(empty.feed(false)==Endpoint::Reason::NoSpeech);
    assert(!empty.speech_seen());
    // A quiet but positively classified short yes/no is sufficient speech.
    Endpoint yes(8000);
    for(int i=0;i<3;++i) yes.feed(true);
    for(int i=0;i<24;++i) yes.feed(false);
    assert(yes.finished() && std::strcmp(yes.reason(),"silence")==0);
    // Long speech is retained past the old 4.8 s window but has a hard cap.
    Endpoint long_turn(8000);
    for (int i=0;i<266;++i) assert(long_turn.feed(true)==Endpoint::Reason::Listening);
    assert(long_turn.feed(true)==Endpoint::Reason::Limit);
    // New turns never reuse previous speech state.
    Endpoint next(8000);
    assert(!next.speech_seen() && !next.finished());
}
