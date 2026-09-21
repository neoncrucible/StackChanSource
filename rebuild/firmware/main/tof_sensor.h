#pragma once
#include "sensor_bus.h"
#include "vl53l1x_init.h"
#include <algorithm>

namespace kadence_sensors {
struct TofSnapshot {
    Health health = Health::Starting;
    uint32_t sequence = 0, sampled_ms = 0, errors = 0;
    uint16_t distance_mm = 0;
    uint8_t raw_status = 0;
    bool valid = false;
};

// Fixed Unit ToF4M wiring: channel 1 / VL53L1X 0x29. ST ULD register
// sequence, split into one isolated transaction per worker turn. No busy waits,
// dynamic allocation, GPIO interrupts, offset/xtalk calibration or behavioural actions.
class TofSensor {
public:
    struct Step { bool failed = false; bool isolated = true; };
    TofSensor(Bus& bus, uint8_t address) : hub_(bus, address) {}
    const TofSnapshot& snapshot() const { return snapshot_; }
    Step step(uint64_t now, const Snapshot& bus) {
        if (bus.hub != Health::Ready || bus.channels[1].health != Health::Ready ||
            !(bus.channels[1].mask & 1U)) {
            snapshot_.health = Health::Unavailable;
            invalidate(); phase_ = Phase::Identity; index_ = 0;
            return {};
        }
        if (now < due_) return {};
        uint8_t data[17]{};
        uint16_t reg = 0;
        size_t size = 1;
        bool read = false;
        switch (phase_) {
        case Phase::Identity:
            snapshot_.health = Health::Starting; invalidate();
            deadline_ = now + WaitMs; reg = 0x010f; size = 2; read = true; break;
        case Phase::Boot: reg = 0x00e5; read = true; break;
        case Phase::Stop: reg = 0x0087; break;
        case Phase::Defaults:
            reg = 0x002d + index_;
            size = std::min<size_t>(16, sizeof(TofDefaults) - index_);
            std::copy_n(TofDefaults + index_, size, data);
            // M5's reference uses Pololu init(io_2v8=true). Retain AVDD I/O
            // mode at 0x002e rather than the old ULD table's 1.8 V default.
            if (index_ == 0) data[1] |= 1U;
            break;
        case Phase::CalStart: case Phase::Start: reg = 0x0087; data[0] = 0x40; break;
        case Phase::CalWait: case Phase::Ready: reg = 0x0031; read = true; break;
        case Phase::CalClear: case Phase::Clear: reg = 0x0086; data[0] = 1; break;
        case Phase::CalStop: reg = 0x0087; break;
        case Phase::VhvBound: reg = 0x0008; data[0] = 9; break;
        case Phase::VhvTemp: reg = 0x000b; break;
        // Defaults select long distance mode. Explicit 200 ms timing budget,
        // then a calibrated 250 ms intermeasurement period (must exceed budget).
        case Phase::BudgetA: reg = 0x005e; size = 2; data[0] = 2; data[1] = 0xd9; break;
        case Phase::BudgetB: reg = 0x0061; size = 2; data[0] = 2; data[1] = 0xf8; break;
        case Phase::Oscillator: reg = 0x00de; size = 2; read = true; break;
        case Phase::Period:
            reg = 0x006c; size = 4;
            for (size_t i = 0; i < 4; ++i) data[i] = static_cast<uint8_t>(period_ >> (24 - i * 8));
            break;
        case Phase::Result:
            // One coherent result block; never clear the interrupt between
            // reading status and distance. No stale distance on a failed read.
            reg = 0x0089; size = 17; read = true; break;
        }
        const auto result = hub_.register16_io(1, 0x29, reg, data, size, read);
        if (result.result != Result::Ack || !result.isolated) return fault(now, result.isolated);
        due_ = now + 20;
        switch (phase_) {
        case Phase::Identity:
            // Model 0xEA / module type 0xCC, as checked by M5's Pololu driver.
            if (word(data) != 0xeacc) return fault(now, true);
            phase_ = Phase::Boot; break;
        case Phase::Boot:
            if (data[0] & 1U) phase_ = Phase::Stop;
            else if (now >= deadline_) return fault(now, true);
            break;
        case Phase::Stop: index_ = 0; phase_ = Phase::Defaults; break;
        case Phase::Defaults:
            index_ += size;
            if (index_ == sizeof(TofDefaults)) phase_ = Phase::CalStart;
            break;
        case Phase::CalStart: deadline_ = now + WaitMs; phase_ = Phase::CalWait; break;
        case Phase::CalWait:
            // Table programs active-high data-ready (GPIO_HV_MUX_CTRL=0x01).
            if (data[0] & 1U) phase_ = Phase::CalClear;
            else if (now >= deadline_) return fault(now, true);
            break;
        case Phase::CalClear: phase_ = Phase::CalStop; break;
        case Phase::CalStop: phase_ = Phase::VhvBound; break;
        case Phase::VhvBound: phase_ = Phase::VhvTemp; break;
        case Phase::VhvTemp: phase_ = Phase::BudgetA; break;
        case Phase::BudgetA: phase_ = Phase::BudgetB; break;
        case Phase::BudgetB: phase_ = Phase::Oscillator; break;
        case Phase::Oscillator: {
            const auto clock = word(data) & 0x03ffU;
            if (!clock) return fault(now, true);
            period_ = clock * 250U * 1075U / 1000U;
            phase_ = Phase::Period; break;
        }
        case Phase::Period: phase_ = Phase::Start; break;
        case Phase::Start: deadline_ = now + WaitMs; phase_ = Phase::Ready; break;
        case Phase::Ready:
            if (data[0] & 1U) phase_ = Phase::Result;
            else if (now >= deadline_) return fault(now, true);
            break;
        case Phase::Result:
            pending_status_ = data[0] & 0x1f;
            pending_distance_ = word(data + 13);
            pending_ms_ = static_cast<uint32_t>(now);
            phase_ = Phase::Clear; break;
        case Phase::Clear:
            snapshot_.health = Health::Ready;
            snapshot_.raw_status = pending_status_;
            // ULD maps raw status 9 to valid. Reject other status codes and
            // readings outside this unit's advertised 40..4000 mm interval.
            snapshot_.valid = pending_status_ == 9 && pending_distance_ >= 40 && pending_distance_ <= 4000;
            snapshot_.distance_mm = snapshot_.valid ? pending_distance_ : 0;
            snapshot_.sampled_ms = pending_ms_; increment(snapshot_.sequence);
            deadline_ = now + WaitMs; phase_ = Phase::Ready; break;
        }
        return {};
    }
private:
    enum class Phase { Identity, Boot, Stop, Defaults, CalStart, CalWait,
        CalClear, CalStop, VhvBound, VhvTemp, BudgetA, BudgetB, Oscillator,
        Period, Start, Ready, Result, Clear };
    // Discovery can occupy ~2.3 s. This deadline tolerates a normal sweep
    // while bounding a sensor that acknowledges I2C but never produces data.
    static constexpr uint64_t WaitMs = 5000;
    static uint16_t word(const uint8_t* data) { return (uint16_t(data[0]) << 8) | data[1]; }
    void invalidate() { snapshot_.valid = false; snapshot_.distance_mm = 0; snapshot_.raw_status = 0; }
    Step fault(uint64_t now, bool isolated) {
        snapshot_.health = Health::Fault; invalidate(); increment(snapshot_.errors);
        phase_ = Phase::Identity; index_ = 0; due_ = now + QuarantineMs;
        return {true, isolated};
    }
    Pca9548a hub_;
    TofSnapshot snapshot_{};
    Phase phase_ = Phase::Identity;
    size_t index_ = 0;
    uint64_t due_ = 0, deadline_ = 0;
    uint32_t period_ = 0, pending_ms_ = 0;
    uint16_t pending_distance_ = 0;
    uint8_t pending_status_ = 0;
};
}
