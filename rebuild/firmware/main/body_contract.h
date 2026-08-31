#pragma once

#include <algorithm>
#include <cstdint>

namespace kade_body_contract {

inline constexpr int kDisplayWidth = 320;
inline constexpr int kDisplayHeight = 240;
inline constexpr int kAudioSampleRateHz = 16000;
inline constexpr int kAudioChannels = 1;

inline constexpr int kSafeYawMinTenths = -320;
inline constexpr int kSafeYawMaxTenths = 320;
inline constexpr int kSafePitchMinTenths = 30;
inline constexpr int kSafePitchMaxTenths = 870;
inline constexpr int kMinMotionSpeed = 120;
inline constexpr int kMaxMotionSpeed = 850;
inline constexpr int kDefaultMotionSpeed = 650;
inline constexpr int kPositionToleranceTenths = 40;

// These are policy invariants, not tunables.
inline constexpr bool kPreserveStoredZeroCalibration = true;
inline constexpr bool kReleaseTorqueAfterMotion = true;

struct MotionTarget {
    int yaw;
    int pitch;
    int speed;
};

constexpr MotionTarget clamp_motion(int yaw, int pitch, int speed)
{
    return {
        std::clamp(yaw, kSafeYawMinTenths, kSafeYawMaxTenths),
        std::clamp(pitch, kSafePitchMinTenths, kSafePitchMaxTenths),
        std::clamp(speed, kMinMotionSpeed, kMaxMotionSpeed),
    };
}

static_assert(kDisplayWidth == 320 && kDisplayHeight == 240);
static_assert(kAudioSampleRateHz == 16000 && kAudioChannels == 1);
static_assert(kPreserveStoredZeroCalibration);
static_assert(kReleaseTorqueAfterMotion);

}  // namespace kade_body_contract
