#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include <hal/hal.h>
#include <mooncake_log.h>
#include <stackchan/stackchan.h>

#include "safe_motion_foundation.h"

namespace kadence_motion_controller {

constexpr const char* kLogTag = "KADENCE-MOTION-CTRL";
constexpr uint32_t kStepTimeoutMs = 4500;

struct MotionStep {
    int yaw_offset;
    int pitch_offset;
    int speed;
    uint32_t hold_ms;
};

enum class Behaviour : uint8_t {
    None,
    Nod,
    Shake,
    Scan,
};

enum class State : uint8_t {
    Idle,
    Moving,
    Holding,
    Complete,
    Failed,
};

class Controller {
public:
    bool start(Behaviour behaviour)
    {
        if (isBusy()) {
            return false;
        }

        _behaviour = behaviour;
        _step_index = 0;
        _state = State::Idle;
        _failed = false;
        select_sequence();

        if (_steps == nullptr || _step_count == 0) {
            _state = State::Failed;
            _failed = true;
            return false;
        }

        auto& motion = GetStackChan().motion();
        kadence_motion::prepare_controlled_move(motion);
        command_current_step();
        return true;
    }

    void update()
    {
        auto& motion = GetStackChan().motion();
        motion.update();

        const uint32_t now = GetHAL().millis();

        if (_state == State::Moving) {
            if (static_cast<int32_t>(now - _deadline_ms) >= 0) {
                fail("motion step timed out");
                return;
            }

            if (!motion.isMoving()) {
                _state = State::Holding;
                _deadline_ms = now + current_step().hold_ms;
            }
            return;
        }

        if (_state == State::Holding && static_cast<int32_t>(now - _deadline_ms) >= 0) {
            ++_step_index;
            if (_step_index >= _step_count) {
                finish();
                return;
            }
            command_current_step();
        }
    }

    void cancel()
    {
        auto& motion = GetStackChan().motion();
        kadence_motion::stop_and_release(motion);
        _state = State::Idle;
        _behaviour = Behaviour::None;
        _steps = nullptr;
        _step_count = 0;
        _step_index = 0;
    }

    bool isBusy() const
    {
        return _state == State::Moving || _state == State::Holding;
    }

    bool isComplete() const
    {
        return _state == State::Complete;
    }

    bool hasFailed() const
    {
        return _failed;
    }

    State state() const
    {
        return _state;
    }

private:
    // Offsets are relative to Project Kadence rest [80,300]. They follow the
    // official factory pitch model: positive pitch offsets look upward and
    // negative pitch offsets look downward.
    static constexpr std::array<MotionStep, 5> kNod = {{
        {0, 0, 700, 140},
        {0, -200, 700, 120},
        {0, 200, 700, 120},
        {0, -200, 700, 120},
        {0, 0, 700, 220},
    }};

    static constexpr std::array<MotionStep, 5> kShake = {{
        {0, 0, 700, 140},
        {-180, 0, 700, 120},
        {180, 0, 700, 120},
        {-150, 0, 700, 120},
        {0, 0, 700, 220},
    }};

    static constexpr std::array<MotionStep, 5> kScan = {{
        {0, 0, 650, 180},
        {-220, 120, 650, 220},
        {0, -120, 650, 180},
        {220, 120, 650, 220},
        {0, 0, 650, 260},
    }};

    void select_sequence()
    {
        switch (_behaviour) {
            case Behaviour::Nod:
                _steps = kNod.data();
                _step_count = kNod.size();
                break;
            case Behaviour::Shake:
                _steps = kShake.data();
                _step_count = kShake.size();
                break;
            case Behaviour::Scan:
                _steps = kScan.data();
                _step_count = kScan.size();
                break;
            case Behaviour::None:
            default:
                _steps = nullptr;
                _step_count = 0;
                break;
        }
    }

    const MotionStep& current_step() const
    {
        return _steps[_step_index];
    }

    void command_current_step()
    {
        auto& motion = GetStackChan().motion();
        const MotionStep& requested = current_step();
        const kadence_motion::SafeTarget safe =
            kadence_motion::offset_from_rest(requested.yaw_offset, requested.pitch_offset);
        const int speed = kadence_motion::clamp_speed(requested.speed);

        motion.moveWithSpeed(safe.yaw, safe.pitch, speed);
        _state = State::Moving;
        _deadline_ms = GetHAL().millis() + kStepTimeoutMs;

        mclog::tagInfo(kLogTag,
                       "behaviour={} step={}/{} offset=[{},{}] target=[{},{}] speed={}",
                       static_cast<int>(_behaviour),
                       _step_index + 1,
                       _step_count,
                       requested.yaw_offset,
                       requested.pitch_offset,
                       safe.yaw,
                       safe.pitch,
                       speed);
    }

    void finish()
    {
        auto& motion = GetStackChan().motion();
        kadence_motion::stop_and_release(motion);
        _state = State::Complete;
        mclog::tagInfo(kLogTag, "behaviour complete at rest pose; torque released");
    }

    void fail(const char* reason)
    {
        auto& motion = GetStackChan().motion();
        kadence_motion::stop_and_release(motion);
        _state = State::Failed;
        _failed = true;
        mclog::tagError(kLogTag, "{}; torque released", reason);
    }

    Behaviour _behaviour = Behaviour::None;
    State _state = State::Idle;
    const MotionStep* _steps = nullptr;
    std::size_t _step_count = 0;
    std::size_t _step_index = 0;
    uint32_t _deadline_ms = 0;
    bool _failed = false;
};

}  // namespace kadence_motion_controller
