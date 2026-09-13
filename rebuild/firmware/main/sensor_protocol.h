#pragma once
#include "cJSON.h"
#include "sensor_bus.h"
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
enum class Request { Other, Invalid, Status };
inline Request parse_request(const cJSON* root) {
    const auto* name = cJSON_GetObjectItemCaseSensitive(root, "name");
    if (!cJSON_IsString(name) || std::strcmp(name->valuestring, "sensors.status")) return Request::Other;
    const auto* id = cJSON_GetObjectItemCaseSensitive(root, "id");
    const auto* version = cJSON_GetObjectItemCaseSensitive(root, "v");
    const auto* kind = cJSON_GetObjectItemCaseSensitive(root, "kind");
    const auto* payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
    if (!cJSON_IsString(id) || !id->valuestring[0] || std::strlen(id->valuestring) >= 48 ||
        !cJSON_IsNumber(version) || version->valuedouble != 1 ||
        !cJSON_IsString(kind) || std::strcmp(kind->valuestring, "command") ||
        !cJSON_IsObject(payload) || cJSON_GetArraySize(payload) != 0) return Request::Invalid;
    return Request::Status;
}
}
