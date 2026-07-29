#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include <esp_random.h>
#include <hal/hal.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

#include "safe_motion_foundation.h"

namespace kadence_idle_motion {

constexpr const char* kLogTag = "KADENCE-IDLE-MOTION";

// Production cadence: each completed gesture schedules a fresh random delay.
// Idle movement remains active until explicitly disabled or power is removed.
constexpr uint32_t kIntervalMinimumMs = 90000;
constexpr uint32_t kIntervalMaximumMs = 180000;
constexpr uint32_t kMotionTimeoutMs = 4500;

struct GestureTarget {
    int yaw;
    int pitch;
    const char* label;
};

enum class State : uint8_t {
    Disabled,
    Waiting,
    MovingOut,
    Holding,
    Returning,
};

class Service {
public:
    void initialise()
    {
        _enabled = false;
        _state = State::Disabled;
        _next_tick_ms = 0;
        _deadline_ms = 0;
        cancel_and_release();
        mclog::tagInfo(kLogTag, "initialised disabled; servo torque released");
    }

    bool enabled() const
    {
        return _enabled;
    }

    bool movement_active() const
    {
        return _state == State::MovingOut ||
               _state == State::Holding ||
               _state == State::Returning;
    }

    void set_enabled(bool enabled)
    {
        if (enabled == _enabled) {
            if (!enabled) {
                cancel_and_release();
            }
            return;
        }

        if (!enabled) {
            _enabled = false;
            _state = State::Disabled;
            _next_tick_ms = 0;
            _deadline_ms = 0;
            cancel_and_release();
            mclog::tagInfo(kLogTag, "disabled; pending movement cleared and torque released");
            return;
        }

        // Enabling movement never energises a servo by itself. The scheduler
        // waits for the first production interval and enables torque only when
        // an actual gesture begins.
        cancel_and_release();
        _enabled = true;
        _state = State::Waiting;
        schedule_next(GetHAL().millis());
        mclog::tagInfo(kLogTag,
                       "enabled; torque remains released while waiting for next gesture");
    }

    void toggle()
    {
        set_enabled(!_enabled);
    }

    void update()
    {
        if (!_enabled) {
            return;
        }

        auto& motion = GetStackChan().motion();
        const uint32_t now = GetHAL().millis();

        switch (_state) {
            case State::Waiting:
                if (!deadline_reached(now, _next_tick_ms)) {
                    return;
                }

                // Match the official idle-motion lifecycle: never queue a new
                // command on top of an existing movement.
                if (motion.isMoving()) {
                    _next_tick_ms = now + 500;
                    return;
                }

                begin_random_gesture(now);
                return;

            case State::MovingOut:
                if (deadline_reached(now, _deadline_ms)) {
                    fail_closed("idle gesture outbound movement timed out");
                    return;
                }

                if (!motion.isMoving()) {
                    const auto current = motion.getCurrentAngles();
                    const kadence_motion::SafeTarget actual{current.x, current.y};
                    if (!kadence_motion::readback_matches(_active_target, actual)) {
                        mclog::tagError(kLogTag,
                                        "idle gesture read-back failed: target=[{},{}], actual=[{},{}]",
                                        _active_target.yaw,
                                        _active_target.pitch,
                                        actual.yaw,
                                        actual.pitch);
                        fail_closed("idle gesture target was not reached");
                        return;
                    }

                    _state = State::Holding;
                    _deadline_ms = now + _hold_ms;
                }
                return;

            case State::Holding:
                if (!deadline_reached(now, _deadline_ms)) {
                    return;
                }

                // Keep torque enabled only long enough to return to the approved
                // Project Kadence rest pose, then release it immediately.
                motion.moveWithSpeed(kadence_motion::kRestYaw,
                                     kadence_motion::kRestPitch,
                                     _speed);
                _state = State::Returning;
                _deadline_ms = now + kMotionTimeoutMs;
                mclog::tagInfo(kLogTag,
                               "returning to rest [{},{}] at speed {}",
                               kadence_motion::kRestYaw,
                               kadence_motion::kRestPitch,
                               _speed);
                return;

            case State::Returning:
                if (deadline_reached(now, _deadline_ms)) {
                    fail_closed("idle gesture return movement timed out");
                    return;
                }

                if (!motion.isMoving()) {
                    const auto current = motion.getCurrentAngles();
                    const kadence_motion::SafeTarget actual{current.x, current.y};
                    const kadence_motion::SafeTarget rest{
                        kadence_motion::kRestYaw,
                        kadence_motion::kRestPitch,
                    };
                    if (!kadence_motion::readback_matches(rest, actual)) {
                        mclog::tagError(kLogTag,
                                        "idle rest read-back failed: target=[{},{}], actual=[{},{}]",
                                        rest.yaw,
                                        rest.pitch,
                                        actual.yaw,
                                        actual.pitch);
                        fail_closed("idle gesture did not return to rest");
                        return;
                    }

                    kadence_motion::stop_and_release(motion);
                    _state = State::Waiting;
                    schedule_next(now);
                    mclog::tagInfo(kLogTag,
                                   "idle gesture complete at rest; torque released");
                }
                return;

            case State::Disabled:
            default:
                return;
        }
    }

private:
    static constexpr std::array<GestureTarget, 8> kGestures = {{
        {20, 300, "small glance left"},
        {140, 300, "small glance right"},
        {80, 360, "slight look up"},
        {80, 240, "slight look down"},
        {30, 350, "small upper-left glance"},
        {130, 350, "small upper-right glance"},
        {30, 250, "small lower-left glance"},
        {130, 250, "small lower-right glance"},
    }};

    static bool deadline_reached(uint32_t now, uint32_t deadline)
    {
        return static_cast<int32_t>(now - deadline) >= 0;
    }

    static uint32_t random_between(uint32_t minimum, uint32_t maximum)
    {
        return minimum + (esp_random() % (maximum - minimum + 1));
    }

    void schedule_next(uint32_t now)
    {
        const uint32_t delay = random_between(kIntervalMinimumMs, kIntervalMaximumMs);
        _next_tick_ms = now + delay;
        mclog::tagInfo(kLogTag, "next idle gesture scheduled in {} ms", delay);
    }

    void begin_random_gesture(uint32_t now)
    {
        auto& motion = GetStackChan().motion();
        const std::size_t index = static_cast<std::size_t>(esp_random() % kGestures.size());
        const GestureTarget& requested = kGestures[index];

        _active_target = kadence_motion::clamp_target(requested.yaw, requested.pitch);
        _speed = static_cast<int>(random_between(220, 280));
        _hold_ms = random_between(250, 450);

        kadence_motion::prepare_controlled_move(motion);
        motion.moveWithSpeed(_active_target.yaw, _active_target.pitch, _speed);
        _state = State::MovingOut;
        _deadline_ms = now + kMotionTimeoutMs;

        mclog::tagInfo(kLogTag,
                       "starting {}: target=[{},{}], speed={}, hold={} ms",
                       requested.label,
                       _active_target.yaw,
                       _active_target.pitch,
                       _speed,
                       _hold_ms);
    }

    void cancel_and_release()
    {
        auto& motion = GetStackChan().motion();
        kadence_motion::stop_and_release(motion);
    }

    void fail_closed(const char* reason)
    {
        _enabled = false;
        _state = State::Disabled;
        _next_tick_ms = 0;
        _deadline_ms = 0;
        cancel_and_release();
        mclog::tagError(kLogTag, "{}; idle motion disabled and torque released", reason);
    }

    bool _enabled = false;
    State _state = State::Disabled;
    uint32_t _next_tick_ms = 0;
    uint32_t _deadline_ms = 0;
    uint32_t _hold_ms = 0;
    int _speed = 240;
    kadence_motion::SafeTarget _active_target{
        kadence_motion::kRestYaw,
        kadence_motion::kRestPitch,
    };
};

}  // namespace kadence_idle_motion
