#pragma once

namespace kadence_unitv2 {

bool start();
bool route(const char* raw, void (*emit)(const char*));

}  // namespace kadence_unitv2
