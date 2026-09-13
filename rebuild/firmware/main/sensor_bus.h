#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace kadence_sensors {
constexpr size_t ChannelCount = 6;
// Address evidence only; a responding address does not identify a chip or
// establish that a measurement is valid. Bit order is part of schema 1.
constexpr std::array<uint8_t, 8> Addresses{0x29, 0x44, 0x45, 0x5c, 0x70, 0x73, 0x76, 0x77};
constexpr uint64_t ScanIntervalMs = 5000;
constexpr uint64_t QuarantineMs = 60000;

enum class Result { Ack, Nack, Error };
enum class Health { Starting, Ready, Absent, Fault, Quarantined, Unavailable };
inline const char* health_name(Health value) {
    switch (value) {
    case Health::Starting: return "starting";
    case Health::Ready: return "ready";
    case Health::Absent: return "absent";
    case Health::Fault: return "fault";
    case Health::Quarantined: return "quarantined";
    default: return "unavailable";
    }
}
inline void increment(uint32_t& value) { if (value != UINT32_MAX) ++value; }

struct Channel {
    Health health = Health::Unavailable;
    uint8_t mask = 0;
    uint32_t errors = 0;
};
struct Snapshot {
    uint32_t sequence = 0, sampled_ms = 0, hub_errors = 0;
    uint8_t hub_address = 0x70, upstream_mask = 0;
    Health hub = Health::Starting;
    std::array<Channel, ChannelCount> channels{};
};

// One worker owns this interface and every select / transaction / deselect.
// Implementations must bound every call. No internal board bus or voice access.
class Bus {
public:
    virtual ~Bus() = default;
    virtual Result probe(uint8_t address) = 0;
    virtual bool register_io(uint8_t, uint8_t, uint8_t*, size_t, bool) { return false; }
    virtual bool write_switch(uint8_t address, uint8_t mask) = 0;
    virtual bool read_switch(uint8_t address, uint8_t& mask) = 0;
};

class Pca9548a {
public:
    Pca9548a(Bus& bus, uint8_t address) : bus_(bus), address_(address) {}
    Result begin() {
        if (address_ < 0x70 || address_ > 0x77) return Result::Error;
        const auto present = bus_.probe(address_);
        if (present != Result::Ack) return present;
        return set_mask(0) ? Result::Ack : Result::Error;
    }
    struct Probe { Result result; bool isolated; };
    Probe probe_channel(size_t channel, uint8_t address) {
        if (channel >= ChannelCount || address == address_ || address < 8 || address >= 0x78)
            return {Result::Error, false};
        // Channel selection requires its own STOP before downstream traffic.
        if (!set_mask(static_cast<uint8_t>(1U << channel))) {
            set_mask(0); // best effort, never trust an unsuccessful selection
            return {Result::Error, false};
        }
        const auto result = bus_.probe(address);
        // Always isolate, including NACK/timeout. A stuck-low physical bus may
        // prevent this: report a hub fault, never scan another channel blindly.
        return {result, set_mask(0)};
    }
    Probe register_io(size_t channel, uint8_t address, uint8_t reg, uint8_t* data, size_t size, bool read) {
        if (channel >= ChannelCount || address == address_ || !data || !size || size > 2)
            return {Result::Error, false};
        if (!set_mask(static_cast<uint8_t>(1U << channel))) {
            set_mask(0);
            return {Result::Error, false};
        }
        const bool ok = bus_.register_io(address, reg, data, size, read);
        return {ok ? Result::Ack : Result::Error, set_mask(0)};
    }
private:
    bool set_mask(uint8_t mask) {
        uint8_t actual = 0xff;
        return bus_.write_switch(address_, mask) && bus_.read_switch(address_, actual) && actual == mask;
    }
    Bus& bus_;
    uint8_t address_;
};

// Bounded incremental discovery. Each step performs at most one target probe.
// A complete immutable snapshot is published only at sweep end or hub failure.
class Discovery {
public:
    Discovery(Bus& bus, uint8_t address = 0x70) : bus_(bus), hub_(bus, address) {
        current_.hub_address = address;
    }
    const Snapshot& snapshot() const { return current_; }
    bool idle() const { return phase_ == Phase::Wait; }
    void measurement_fault(uint64_t now, bool isolated, size_t channel) {
        pending_ = current_;
        if (!isolated) { fail_hub(now, Result::Error); return; }
        increment(pending_.channels[channel].errors);
        pending_.channels[channel].health = Health::Quarantined;
        pending_.channels[channel].mask = 0;
        retry_channel_[channel] = now + QuarantineMs;
        publish(now);
    }
    bool step(uint64_t now) {
        if (phase_ == Phase::Wait) {
            if (now < next_scan_) return false;
            pending_ = current_;
            pending_.upstream_mask = 0;
            for (auto& channel : pending_.channels) {
                channel.mask = 0;
                channel.health = Health::Unavailable;
            }
            const auto result = hub_.begin();
            if (result != Result::Ack) return fail_hub(now, result);
            pending_.hub = Health::Ready;
            target_ = channel_ = 0;
            phase_ = Phase::Upstream;
            return false;
        }
        if (phase_ == Phase::Upstream) {
            const auto address = Addresses[target_];
            const auto result = address == pending_.hub_address ? Result::Ack : bus_.probe(address);
            if (result == Result::Error) return fail_hub(now, result);
            if (result == Result::Ack) pending_.upstream_mask |= 1U << target_;
            if (++target_ == Addresses.size()) {
                target_ = 0;
                phase_ = Phase::Channels;
            }
            return false;
        }
        auto& channel = pending_.channels[channel_];
        if (now < retry_channel_[channel_]) {
            channel.health = Health::Quarantined;
            return next_channel(now);
        }
        channel.health = Health::Ready;
        // Anything responding with all channels off is upstream (or collides
        // with the configured hub). Never claim it belongs to six channels.
        if (!(pending_.upstream_mask & (1U << target_))) {
            const auto probe = hub_.probe_channel(channel_, Addresses[target_]);
            if (!probe.isolated) return fail_hub(now, Result::Error);
            if (probe.result == Result::Error) {
                channel.mask = 0;
                increment(channel.errors);
                channel.health = Health::Quarantined;
                retry_channel_[channel_] = now + QuarantineMs;
                return next_channel(now);
            }
            if (probe.result == Result::Ack) channel.mask |= 1U << target_;
        }
        if (++target_ == Addresses.size()) return next_channel(now);
        return false;
    }
private:
    enum class Phase { Wait, Upstream, Channels };
    bool publish(uint64_t now) {
        pending_.sequence = current_.sequence;
        increment(pending_.sequence);
        pending_.sampled_ms = static_cast<uint32_t>(now);
        current_ = pending_;
        phase_ = Phase::Wait;
        next_scan_ = now + ScanIntervalMs;
        return true;
    }
    bool fail_hub(uint64_t now, Result result) {
        pending_.hub = result == Result::Nack ? Health::Absent : Health::Fault;
        if (result == Result::Error) increment(pending_.hub_errors);
        pending_.upstream_mask = 0;
        for (auto& channel : pending_.channels) {
            channel.health = Health::Unavailable;
            channel.mask = 0;
        }
        return publish(now);
    }
    bool next_channel(uint64_t now) {
        target_ = 0;
        if (++channel_ == ChannelCount) return publish(now);
        return false;
    }
    Bus& bus_;
    Pca9548a hub_;
    Snapshot current_{}, pending_{};
    Phase phase_ = Phase::Wait;
    size_t channel_ = 0, target_ = 0;
    uint64_t next_scan_ = 0;
    std::array<uint64_t, ChannelCount> retry_channel_{};
};
}
