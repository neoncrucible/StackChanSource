#pragma once
#include <cstddef>

namespace kadence_control {
// Includes JSON escaping, the longest supported settings/status payload, newline
// and cJSON's preallocated-print margin. Both RX and TX use the same contract.
constexpr std::size_t FrameBytes = 1024;
}
