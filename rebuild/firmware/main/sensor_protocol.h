#pragma once
#include "cJSON.h"
#include "sensor_bus.h"
#include "gesture_sensor.h"
#include "tof_sensor.h"
#include <cstring>

namespace kadence_sensors {
inline cJSON* status_payload(const Snapshot& snapshot, uint32_t now) {
    cJSON* p = cJSON_CreateObject();
    if (!p) return nullptr;
    cJSON_AddBoolToObject(p, "ok", true); // query succeeded, independent of hardware health
    cJSON_AddNumberToObject(p, "schema", 1);
    cJSON_AddNumberToObject(p, "seq", snapshot.sequence);
    cJSON_AddNumberToObject(p, "age_ms", static_cast<uint32_t>(now - snapshot.sampled_ms));
    cJSON_AddNumberToObject(p, "hub_address", snapshot.hub_address);
    cJSON_AddStringToObject(p, "hub", health_name(snapshot.hub));
    cJSON_AddNumberToObject(p, "hub_errors", snapshot.hub_errors);
    cJSON_AddNumberToObject(p, "upstream_mask", snapshot.upstream_mask);
    cJSON* channels = cJSON_AddArrayToObject(p, "channels");
    if (!channels) { cJSON_Delete(p); return nullptr; }
    for (const auto& channel : snapshot.channels) {
        cJSON* item = cJSON_CreateObject();
        if (!item) { cJSON_Delete(p); return nullptr; }
        cJSON_AddStringToObject(item, "state", health_name(channel.health));
        cJSON_AddNumberToObject(item, "mask", channel.mask);
        cJSON_AddNumberToObject(item, "errors", channel.errors);
        cJSON_AddItemToArray(channels, item);
    }
    return p;
}
inline cJSON* gesture_payload(const GestureSnapshot& s, uint32_t now) {
    auto* p = cJSON_CreateObject();
    if (!p) return nullptr;
    cJSON_AddBoolToObject(p, "ok", true);
    cJSON_AddNumberToObject(p, "schema", 1);
    cJSON_AddStringToObject(p, "state", health_name(s.health));
    cJSON_AddNumberToObject(p, "channel", 0);
    cJSON_AddNumberToObject(p, "address", 0x73);
    cJSON_AddNumberToObject(p, "seq", s.sequence);
    cJSON_AddNumberToObject(p, "age_ms", static_cast<uint32_t>(now-s.sampled_ms));
    cJSON_AddNumberToObject(p, "event_seq", s.event_sequence);
    cJSON_AddNumberToObject(p, "event_age_ms", static_cast<uint32_t>(now-s.event_ms));
    cJSON_AddNumberToObject(p, "flags", s.flags);
    return p;
}
inline cJSON* tof_payload(const TofSnapshot& s, uint32_t now) {
    auto* p = cJSON_CreateObject();
    if (!p) return nullptr;
    cJSON_AddBoolToObject(p, "ok", true);
    cJSON_AddNumberToObject(p, "schema", 1);
    cJSON_AddStringToObject(p, "state", health_name(s.health));
    cJSON_AddNumberToObject(p, "channel", 1);
    cJSON_AddNumberToObject(p, "address", 0x29);
    cJSON_AddNumberToObject(p, "seq", s.sequence);
    cJSON_AddNumberToObject(p, "age_ms", static_cast<uint32_t>(now-s.sampled_ms));
    cJSON_AddNumberToObject(p, "errors", s.errors);
    cJSON_AddNumberToObject(p, "raw_status", s.raw_status);
    cJSON_AddBoolToObject(p, "valid", s.valid);
    if (s.valid) cJSON_AddNumberToObject(p, "distance_mm", s.distance_mm);
    else cJSON_AddNullToObject(p, "distance_mm");
    return p;
}
enum class Request { Other, Invalid, Status, Gesture, Tof };
inline Request parse_request(const cJSON* root) {
    const auto* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name)) return Request::Other;
    const bool gesture = !std::strcmp(name->valuestring, "sensors.gesture");
    const bool tof = !std::strcmp(name->valuestring, "sensors.tof");
    if (!gesture && !tof && std::strcmp(name->valuestring, "sensors.status")) return Request::Other;
    const auto* id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const auto* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const auto* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const auto* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    if (!cJSON_IsString(id) || !id->valuestring[0] || std::strlen(id->valuestring) >= 48 ||
        !cJSON_IsNumber(version) || version->valuedouble != 1 ||
        !cJSON_IsString(kind) || std::strcmp(kind->valuestring, "command") ||
        !cJSON_IsObject(payload) || cJSON_GetArraySize(payload) != 0) return Request::Invalid;
    return tof ? Request::Tof : gesture ? Request::Gesture : Request::Status;
}
}
