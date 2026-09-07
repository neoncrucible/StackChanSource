#pragma once
#include <atomic>

namespace kadence_wifi {
enum class Phase { Stopped, Resetting, Connecting, Connected, Failed };
enum class Disconnect { Ignore, Retry, Failed };

class State {
    std::atomic<Phase> phase_{Phase::Stopped};
    std::atomic<int> retries_{0};
    std::atomic<int> reason_{0};
public:
    void begin_reset() { phase_.store(Phase::Resetting); }
    void stopped() { phase_.store(Phase::Stopped); }
    void begin_connect() { retries_.store(0); reason_.store(0); phase_.store(Phase::Connecting); }
    void fail() { phase_.store(Phase::Failed); }
    bool got_ip() {
        Phase expected = Phase::Connecting;
        const bool accepted = phase_.compare_exchange_strong(expected, Phase::Connected) || expected == Phase::Connected;
        if (accepted) reason_.store(0);
        return accepted;
    }
    Disconnect disconnected(int reason) {
        reason_.store(reason);
        const Phase phase = phase_.load();
        if (phase == Phase::Connected) phase_.store(Phase::Stopped);
        if (phase != Phase::Connecting) return Disconnect::Ignore;
        if (retries_.fetch_add(1) < 3) return Disconnect::Retry;
        phase_.store(Phase::Failed);
        return Disconnect::Failed;
    }
    bool reusable(bool matching_credentials, bool has_ip) const {
        return phase_.load() == Phase::Connected && matching_credentials && has_ip;
    }
    int reason() const { return reason_.load(); }
};
}
