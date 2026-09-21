#include "../firmware/main/tof_sensor.h"
#include "../firmware/main/gesture_sensor.h"
#include <cassert>
#include <cstdio>
using namespace kadence_sensors;

struct Fake : Bus {
    uint8_t mask = 0, status = 9;
    uint16_t distance = 500, identity = 0xeacc;
    bool boot = true, ready = true, fail_result = false, fail_clear = false, stuck = false;
    unsigned calls = 0, writes = 0, clears = 0;
    uint32_t period = 0;
    Result probe(uint8_t a) override {
        ++calls;
        return a == 0x70 || (a == 0x29 && mask == 2) || (a == 0x73 && mask == 1) ? Result::Ack : Result::Nack;
    }
    bool write_switch(uint8_t, uint8_t m) override { ++calls; if (stuck && !m) return false; mask = m; return true; }
    bool read_switch(uint8_t, uint8_t& m) override { ++calls; m = mask; return true; }
    bool register_io(uint8_t a, uint8_t reg, uint8_t* d, size_t n, bool read) override {
        ++calls; assert(mask == 1 && a == 0x73 && n <= 2);
        if (read && reg == 0) { d[0] = 0x20; d[1] = 0x76; }
        else if (read && reg == 0x43) { d[0] = 1; d[1] = 0; }
        return true;
    }
    bool register16_io(uint8_t a, uint16_t reg, uint8_t* d, size_t n, bool read) override {
        ++calls; assert(mask == 2 && a == 0x29 && n <= 17);
        if (!read) {
            ++writes;
            if (reg == 0x2d) assert(d[1] & 1U);
            if (reg == 0x86) { ++clears; if (fail_clear) return false; }
            if (reg == 0x6c && n == 4) period = (uint32_t(d[0])<<24) | (uint32_t(d[1])<<16) | (uint32_t(d[2])<<8) | d[3];
        } else if (reg == 0x10f) { assert(n == 2); d[0] = identity >> 8; d[1] = identity; }
        else if (reg == 0xe5) d[0] = boot;
        else if (reg == 0x31) d[0] = ready;
        else if (reg == 0xde) { d[0] = 0; d[1] = 100; }
        else if (reg == 0x89) {
            assert(n == 17); if (fail_result) return false;
            d[0] = status; d[13] = distance >> 8; d[14] = distance;
        } else assert(false);
        return true;
    }
};
Snapshot connected() {
    Snapshot s; s.hub = Health::Ready;
    s.channels[1].health = Health::Ready; s.channels[1].mask = 1;
    return s;
}
void advance(TofSensor& t, Fake& b, const Snapshot& s, uint64_t from, uint64_t until) {
    for (auto now = from; now < until; now += 20) {
        const auto before = b.calls;
        assert(!t.step(now, s).failed);
        assert(b.calls - before <= 5 && b.mask == 0);
    }
}
int main() {
    auto s = connected();
    Fake b; TofSensor t(b, 0x70);
    advance(t, b, Snapshot{}, 0, 100);
    assert(!b.calls && !t.snapshot().valid);
    advance(t, b, s, 100, 1600);
    assert(t.snapshot().valid && t.snapshot().distance_mm == 500 && b.period == 26875);
    // Valid new reading replaces old reading; failed-quality results expose no distance.
    b.distance = 1234; advance(t, b, s, 1600, 1800);
    assert(t.snapshot().distance_mm == 1234);
    b.status = 4; advance(t, b, s, 1800, 2000);
    assert(!t.snapshot().valid && !t.snapshot().distance_mm && t.snapshot().raw_status == 4 && !t.snapshot().errors);
    b.status = 9;
    for (auto distance : {uint16_t(0), uint16_t(39), uint16_t(4001), uint16_t(65535)}) {
        b.distance = distance;
        static uint64_t now = 2000; advance(t, b, s, now, now + 200); now += 200;
        assert(!t.snapshot().valid && !t.snapshot().distance_mm);
    }
    b.distance = 4000; advance(t, b, s, 2800, 3000);
    assert(t.snapshot().valid);
    b.fail_result = true;
    bool failed = false;
    for (uint64_t now = 3000; now < 3200; now += 20) if (t.step(now, s).failed) { failed = true; break; }
    assert(failed && !b.mask && !t.snapshot().valid && t.snapshot().errors == 1);
    const auto calls = b.calls; t.step(5000, s); assert(b.calls == calls);
    b.fail_result = false; advance(t, b, s, 64000, 66000);
    assert(t.snapshot().valid);
    t.step(66000, Snapshot{}); assert(!t.snapshot().valid && t.snapshot().health == Health::Unavailable);

    // A different device at the same I2C address must receive no config writes.
    Fake wrong; wrong.identity = 0xeeac; TofSensor rejected(wrong, 0x70);
    assert(rejected.step(0, s).failed && !wrong.writes && !wrong.mask);
    // An ACKing device that never boots or produces a calibration result is bounded.
    for (bool boot : {false, true}) {
        Fake wait; wait.boot = boot; wait.ready = false; TofSensor timeout(wait, 0x70);
        bool expired = false;
        for (uint64_t now = 0; now < 7000; now += 20) if (timeout.step(now, s).failed) { expired = true; break; }
        assert(expired && !timeout.snapshot().valid && !wait.mask);
    }
    // Clear failure must not publish a pending measurement as a new valid sample.
    Fake clear; TofSensor clear_sensor(clear, 0x70); advance(clear_sensor, clear, s, 0, 1600);
    const auto sequence = clear_sensor.snapshot().sequence; clear.fail_clear = true;
    for (uint64_t now = 1600; now < 1800; now += 20) clear_sensor.step(now, s);
    assert(clear_sensor.snapshot().sequence == sequence && !clear_sensor.snapshot().valid);
    Fake stuck; stuck.stuck = true; TofSensor isolated(stuck, 0x70);
    auto fault = isolated.step(0, s); assert(fault.failed && !fault.isolated);

    // Exercise real discovery + both production drivers under the worker schedule.
    Fake shared; Discovery discovery(shared, 0x70); GestureSensor gesture(shared, 0x70); TofSensor tof(shared, 0x70);
    bool registers = false, tof_turn = false;
    for (uint64_t now = 0; now < 45000; now += 20) {
        const auto before = shared.calls;
        registers = !registers;
        if (!registers) discovery.step(now);
        if (registers && discovery.idle()) {
            tof_turn = !tof_turn;
            if (tof_turn) assert(!tof.step(now, discovery.snapshot()).failed);
            else assert(!gesture.step(now, discovery.snapshot()).failed);
        }
        assert(shared.calls - before <= 5 && !shared.mask);
    }
    assert(tof.snapshot().sequence > 20 && tof.snapshot().valid);
    assert(gesture.snapshot().event_sequence > 5 && gesture.snapshot().health == Health::Ready);
    puts("TOF_SENSOR PASS identity distance quality timeout isolation recovery shared-worker");
}
