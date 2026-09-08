#pragma once
#include <atomic>
#include <cstdint>

namespace {
// All hardware writes happen in the presentation/media owners. Protocol readers
// enqueue commands; these atomics carry only bounded state between the owners.
inline std::atomic<int> g_user_volume{100};
inline std::atomic<bool> g_user_mute{false};
inline std::atomic<bool> g_top_game_active{false};
inline std::atomic<bool> g_top_stop_game{false};
inline std::atomic<int> g_top_note{-1};
inline std::atomic<bool> g_camera_active{false};
bool top_controls_start(void (*emit)(const char*));
void top_controls_tick(uint64_t now_ms);
bool top_controls_route(const char* raw);
bool top_front_cancel();
void top_controls_overlay(uint16_t* pixels, uint64_t now_ms);
}
