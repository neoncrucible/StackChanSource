#pragma once
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "control_frame.h"

namespace {
// Only the media worker sets these. Events use the normal serialized control
// emitter, and name the original command so the host can retire stale phases.
inline void (*g_voice_phase_emit)(const char*) = nullptr;
inline char g_voice_phase_request_id[48]{};
inline uint32_t g_voice_phase_sequence = 0;

void voice_phase(const char* state, uint32_t capture_ms = 0)
{
    if (!g_voice_phase_emit || !g_voice_phase_request_id[0]) return;
    cJSON* root=cJSON_CreateObject();
    cJSON* payload=cJSON_CreateObject();
    if (!root || !payload) { cJSON_Delete(root); cJSON_Delete(payload); return; }
    char id[32]{};
    std::snprintf(id,sizeof(id),"phase-%08lx",static_cast<unsigned long>(++g_voice_phase_sequence));
    cJSON_AddNumberToObject(root,"v",1);
    cJSON_AddStringToObject(root,"id",id);
    cJSON_AddStringToObject(root,"ts","device");
    cJSON_AddStringToObject(root,"kind","event");
    cJSON_AddStringToObject(root,"name","voice.phase");
    cJSON_AddStringToObject(payload,"request_id",g_voice_phase_request_id);
    cJSON_AddStringToObject(payload,"state",state);
    cJSON_AddNumberToObject(payload,"capture_ms",capture_ms);
    cJSON_AddItemToObject(root,"payload",payload);
    char line[kadence_control::FrameBytes]{};
    if (cJSON_PrintPreallocated(root,line,sizeof(line),false)) g_voice_phase_emit(line);
    cJSON_Delete(root);
}
}
