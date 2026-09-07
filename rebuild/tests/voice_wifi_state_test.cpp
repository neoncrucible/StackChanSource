#include "../firmware/main/voice_wifi_state.h"
#include <cassert>
#include <cstdio>

int main() {
    kadence_wifi::State state;
    using Event = kadence_wifi::Disconnect;
    assert(!state.reusable(true, true));
    state.begin_connect();
    assert(state.got_ip());
    assert(state.reusable(true, true));
    assert(!state.reusable(false, true));
    assert(!state.reusable(true, false));
    // Intentional station shutdown must not trigger a reconnect before config.
    state.begin_reset();
    assert(state.disconnected(8) == Event::Ignore);
    assert(!state.got_ip());
    state.stopped();
    state.begin_connect();
    for(int i=0;i<3;++i) assert(state.disconnected(201) == Event::Retry);
    assert(state.disconnected(202) == Event::Failed);
    assert(state.reason() == 202);
    assert(!state.got_ip());
    state.begin_reset();
    assert(state.disconnected(8) == Event::Ignore);
    state.stopped();
    state.begin_connect();
    assert(state.got_ip());
    assert(state.reusable(true, true));
    // A link lost between turns is no longer eligible for reuse.
    assert(state.disconnected(200) == Event::Ignore);
    assert(!state.reusable(true, true));
    state.begin_connect();
    state.fail(); // Cancel while connecting: later events cannot revive it.
    assert(!state.got_ip());
    assert(state.disconnected(8) == Event::Ignore);
    std::puts("VOICE_WIFI_STATE PASS reuse=1 reset_barrier=1 bounded_retries=1 cancellation=1");
}
