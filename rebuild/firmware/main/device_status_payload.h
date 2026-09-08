#pragma once
#include "cJSON.h"
#include <cstdint>

namespace kadence_status {
struct Snapshot {
    int volume=0, maximum=0, brightness=0;
    bool muted=false, quiet=false, reverse=false, sound=false;
    bool leds=false, top_touch=false, front_touch=false, camera_active=false, media_busy=false;
    const char* presentation="idle";
    const char* game="off";
    const char* firmware="unknown";
    int score=0, best=0, zone=-1;
    uint32_t free_heap=0, free_psram=0, touch_seq=0, capture_remaining_ms=0;
};
inline cJSON* payload(const Snapshot& s, bool ok) {
    cJSON* p=cJSON_CreateObject();
    if (!p) return nullptr;
    cJSON_AddBoolToObject(p,"ok",ok);
    cJSON_AddNumberToObject(p,"volume",s.volume);
    cJSON_AddBoolToObject(p,"muted",s.muted);
    cJSON_AddNumberToObject(p,"maximum",s.maximum);
    cJSON_AddNumberToObject(p,"brightness",s.brightness);
    cJSON_AddBoolToObject(p,"quiet",s.quiet);
    cJSON_AddBoolToObject(p,"reverse",s.reverse);
    cJSON_AddBoolToObject(p,"sound",s.sound);
    cJSON_AddBoolToObject(p,"leds",s.leds);
    cJSON_AddBoolToObject(p,"top_touch",s.top_touch);
    cJSON_AddBoolToObject(p,"front_touch",s.front_touch);
    cJSON_AddBoolToObject(p,"camera_active",s.camera_active);
    cJSON_AddBoolToObject(p,"media_busy",s.media_busy);
    cJSON_AddStringToObject(p,"presentation",s.presentation);
    cJSON_AddStringToObject(p,"game",s.game);
    cJSON_AddStringToObject(p,"firmware",s.firmware);
    cJSON_AddNumberToObject(p,"score",s.score);
    cJSON_AddNumberToObject(p,"best",s.best);
    cJSON_AddNumberToObject(p,"zone",s.zone);
    cJSON_AddNumberToObject(p,"free_heap",s.free_heap);
    cJSON_AddNumberToObject(p,"free_psram",s.free_psram);
    cJSON_AddNumberToObject(p,"touch_seq",s.touch_seq);
    cJSON_AddNumberToObject(p,"capture_remaining_ms",s.capture_remaining_ms);
    return p;
}
}
