#pragma once

namespace kadence_sensors {
// Optional service: start failure is diagnostic, never a body boot failure.
void start();
// Serial owner serves a cached snapshot; never runs I2C or waits for the worker.
bool route(const char* raw, void (*emit)(const char*));
}
