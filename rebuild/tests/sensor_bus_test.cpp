#include "../firmware/main/sensor_bus.h"
#include <cassert>
#include <cstdio>
#include <vector>

using namespace kadence_sensors;
struct FakeBus : Bus {
    bool present = true, stuck = false, bad_readback = false, fail_select = false;
    bool stick_on_probe = false;
    uint8_t hub = 0x70, selected = 0, upstream = 0;
    int timeout_channel = -1, calls = 0, downstream_probes = 0;
    std::array<uint8_t, 6> devices{};
    std::vector<uint8_t> writes;
    Result probe(uint8_t address) override {
        ++calls;
        if (stuck) return Result::Error;
        if (address == hub) return present ? Result::Ack : Result::Nack;
        size_t bit = 0;
        while (bit < Addresses.size() && Addresses[bit] != address) ++bit;
        assert(bit < Addresses.size());
        uint8_t found = upstream;
        if (selected) {
            ++downstream_probes;
            if (stick_on_probe) { stuck = true; return Result::Error; }
            assert(!(selected & (selected - 1)) && selected < 64);
            for (size_t ch = 0; ch < 6; ++ch) if (selected & (1U << ch)) {
                if (static_cast<int>(ch) == timeout_channel) return Result::Error;
                found |= devices[ch];
            }
        }
        return found & (1U << bit) ? Result::Ack : Result::Nack;
    }
    bool write_switch(uint8_t address, uint8_t mask) override {
        ++calls;
        assert(address == hub);
        writes.push_back(mask);
        if (stuck || !present || (fail_select && mask)) return false;
        selected = mask;
        return true;
    }
    bool read_switch(uint8_t address, uint8_t& mask) override {
        ++calls;
        assert(address == hub);
        mask = bad_readback ? 0xff : selected;
        return !stuck && present;
    }
};

Snapshot sweep(Discovery& d, FakeBus& bus, uint64_t& now) {
    for (int i = 0; i < 400; ++i, now += 20) {
        bus.calls = 0;
        const bool published = d.step(now);
        assert(bus.calls <= 5); // transaction deadline budget, no unbounded scan
        if (!bus.stuck) assert(bus.selected == 0);
        if (published) { now += 20; return d.snapshot(); }
    }
    assert(false && "discovery never published within bounded sweep");
    return {};
}

int main() {
    uint64_t now = 0;
    FakeBus missing; missing.present = false;
    Discovery absent(missing);
    auto s = sweep(absent, missing, now);
    assert(s.hub == Health::Absent && s.sequence == 1 && s.hub_errors == 0);
    assert(missing.writes.empty() && missing.downstream_probes == 0);
    missing.calls = 0;
    assert(!absent.step(4999) && missing.calls == 0);
    missing.present = true;
    s = sweep(absent, missing, now);
    assert(s.hub == Health::Ready);
    for (const auto& c : s.channels) assert(c.health == Health::Ready && c.mask == 0 && c.errors == 0);

    FakeBus bus; bus.hub = 0x71;
    bus.devices[0] = 2 | 16; // actual ENV III addresses 0x44 and 0x70
    bus.devices[1] = 1;
    bus.devices[5] = 1; // same address on two isolated channels
    bus.upstream = 128;
    Discovery d(bus, 0x71); now = 0;
    s = sweep(d, bus, now);
    assert(s.channels[0].mask == 18 && s.channels[1].mask == 1 && s.channels[5].mask == 1);
    assert(s.upstream_mask == 128 && s.channels[2].mask == 0);
    assert(bus.writes.front() == 0 && bus.writes.back() == 0);

    bus.timeout_channel = 0;
    s = sweep(d, bus, now);
    assert(s.channels[0].health == Health::Quarantined && s.channels[0].mask == 0);
    assert(s.channels[0].errors == 1 && s.channels[5].mask == 1 && s.hub == Health::Ready);
    bus.timeout_channel = -1;
    s = sweep(d, bus, now);
    assert(s.channels[0].health == Health::Quarantined && s.channels[0].errors == 1);
    now += QuarantineMs;
    s = sweep(d, bus, now);
    assert(s.channels[0].health == Health::Ready && s.channels[0].mask == 18);
    bus.devices[1] = 0;
    s = sweep(d, bus, now);
    assert(s.channels[1].mask == 0 && s.channels[5].mask == 1);

    bus.stuck = true;
    s = sweep(d, bus, now);
    assert(s.hub == Health::Fault && s.hub_errors == 1);
    for (const auto& c : s.channels) assert(c.mask == 0 && c.health == Health::Unavailable);
    bus.stuck = false;
    s = sweep(d, bus, now);
    assert(s.hub == Health::Ready);
    bus.present = false;
    s = sweep(d, bus, now);
    assert(s.hub == Health::Absent && s.hub_errors == 1);

    FakeBus wrong; wrong.bad_readback = true;
    Discovery bad(wrong); now = 0;
    s = sweep(bad, wrong, now);
    assert(s.hub == Health::Fault && wrong.downstream_probes == 0);

    FakeBus wire; wire.stick_on_probe = true;
    Discovery blocked(wire); now = 0;
    s = sweep(blocked, wire, now);
    assert(s.hub == Health::Fault && wire.downstream_probes == 1 && wire.selected != 0);
    const auto probes = wire.downstream_probes;
    blocked.step(now + 1000);
    assert(wire.downstream_probes == probes); // no retry storm on a stuck-low bus
    wire.stuck = wire.stick_on_probe = false;
    now += ScanIntervalMs; // recovery happens on the next scheduled hub attempt
    s = sweep(blocked, wire, now);
    assert(s.hub == Health::Ready && wire.selected == 0);
    wrong.bad_readback = false; wrong.fail_select = true;
    s = sweep(bad, wrong, now);
    assert(s.hub == Health::Fault && wrong.downstream_probes == 0);

    FakeBus invalid; Pca9548a hub(invalid, 0x70);
    assert(!hub.probe_channel(6, 0x44).isolated && invalid.calls == 0);
    assert(!hub.probe_channel(0, 0x70).isolated && invalid.calls == 0);
    Pca9548a bad_address(invalid, 0x69);
    assert(bad_address.begin() == Result::Error && invalid.calls == 0);
    Discovery rollover(invalid); now = static_cast<uint64_t>(UINT32_MAX) + 100;
    s = sweep(rollover, invalid, now);
    assert(s.hub == Health::Ready && s.sampled_ms < 2000);
    std::puts("SENSOR_BUS PASS absent=1 recovery=1 isolation=1 duplicates=1 upstream=1 timeout=1 quarantine=1 bounds=1");
}
