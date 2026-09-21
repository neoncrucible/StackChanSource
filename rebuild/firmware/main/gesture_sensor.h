#pragma once
#include "sensor_bus.h"
#include "paj7620_init.h"
namespace kadence_sensors {
struct GestureSnapshot {
    Health health = Health::Starting;
    uint32_t sequence = 0, sampled_ms = 0, event_sequence = 0, event_ms = 0;
    uint16_t flags = 0;
};
class GestureSensor {
public:
    GestureSensor(Bus& bus, uint8_t address) : hub_(bus, address) {}
    struct Step { bool failed = false; bool isolated = true; };
    const GestureSnapshot& snapshot() const { return snapshot_; }
    Step step(uint64_t now, const Snapshot& bus) {
        // Fixed tested wiring; never initialize an arbitrary device on another channel.
        if (bus.hub != Health::Ready || bus.channels[0].health != Health::Ready ||
            !(bus.channels[0].mask & (1U << 5))) {
            snapshot_.health = Health::Unavailable;
            snapshot_.flags = 0;
            phase_ = 0; index_ = 0;
            return {};
        }
        if (now < due_) return {};
        uint8_t data[2]{};
        Pca9548a::Probe result{};
        if (phase_ == 0) {
            snapshot_.health = Health::Starting;
            result = hub_.register_io(0, 0x73, 0xef, data, 1, false);
        } else if (phase_ == 1) {
            result = hub_.register_io(0, 0x73, 0x00, data, 2, true);
            if (result.result == Result::Ack && (data[0] != 0x20 || data[1] != 0x76))
                result.result = Result::Error;
        } else if (phase_ == 2) {
            data[0] = PajInit[index_][1];
            result = hub_.register_io(0, 0x73, PajInit[index_][0], data, 1, false);
        } else if (phase_ == 3) {
            result = hub_.register_io(0, 0x73, 0xef, data, 1, false);
        } else {
            result = hub_.register_io(0, 0x73, 0x43, data, 2, true);
        }
        if (result.result != Result::Ack || !result.isolated) {
            snapshot_.health = Health::Fault; snapshot_.flags = 0;
            phase_ = 0; index_ = 0; due_ = now + QuarantineMs;
            return {true, result.isolated};
        }
        if (phase_ == 2) { if (++index_ == 219) ++phase_; }
        else if (phase_ < 4) ++phase_;
        else {
            snapshot_.health = Health::Ready;
            increment(snapshot_.sequence); snapshot_.sampled_ms = static_cast<uint32_t>(now);
            const uint16_t flags = data[0] | ((data[1] & 1U) << 8);
            if (flags && now >= event_due_) {
                snapshot_.flags = flags; increment(snapshot_.event_sequence);
                snapshot_.event_ms = static_cast<uint32_t>(now);
                event_due_ = now + 250;
            }
        }
        due_ = now + (phase_ == 4 ? 50 : 20);
        return {};
    }
private:
    Pca9548a hub_;
    GestureSnapshot snapshot_{};
    uint8_t phase_ = 0;
    size_t index_ = 0;
    uint64_t due_ = 0, event_due_ = 0;
};
}
