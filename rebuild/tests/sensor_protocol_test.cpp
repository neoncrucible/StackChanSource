#include "../firmware/main/sensor_protocol.h"
#include "../firmware/main/control_frame.h"
#include "../firmware/main/device_ack.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <string>

using namespace kadence_sensors;
int main() {
    Snapshot s;
    s.sequence = s.hub_errors = UINT32_MAX;
    s.hub = Health::Unavailable;
    s.hub_address = 0x77; s.upstream_mask = 255;
    for (auto& c : s.channels) { c.health = Health::Quarantined; c.errors = UINT32_MAX; c.mask = 255; }
    // Worst serialization width, including all six channels and 6-byte JSON
    // escapes for every byte of a maximum-length correlation id.
    const std::string id(47, '\x01');
    std::array<char, kadence_control::FrameBytes + 2> out{};
    out.front() = 'A'; out.back() = 'Z';
    assert(device_ack(id.c_str(), "sensors.status", status_payload(s, UINT32_MAX), out.data() + 1, kadence_control::FrameBytes));
    assert(out.front() == 'A' && out.back() == 'Z');
    cJSON* root = cJSON_Parse(out.data() + 1);
    assert(root);
    assert(id == cJSON_GetObjectItemCaseSensitive(root, "id")->valuestring);
    auto* p = cJSON_GetObjectItemCaseSensitive(root, "payload");
    assert(cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(p, "channels")) == 6);
    assert(cJSON_GetObjectItemCaseSensitive(p, "age_ms")->valuedouble == UINT32_MAX);
    cJSON_Delete(root);
    s.sampled_ms = UINT32_MAX - 10;
    p = status_payload(s, 20);
    assert(cJSON_GetObjectItemCaseSensitive(p, "age_ms")->valueint == 31);
    cJSON_Delete(p);

    const char* good = R"({"v":1,"id":"probe","kind":"command","name":"sensors.status","payload":{}})";
    root = cJSON_Parse(good);
    assert(parse_request(root) == Request::Status);
    cJSON_ReplaceItemInObject(root, "payload", cJSON_CreateArray());
    assert(parse_request(root) == Request::Invalid);
    cJSON_ReplaceItemInObject(root, "payload", cJSON_CreateObject());
    cJSON_AddNumberToObject(cJSON_GetObjectItemCaseSensitive(root, "payload"), "channel", 0);
    assert(parse_request(root) == Request::Invalid);
    cJSON_Delete(root);
    for (const char* key : {"id", "kind", "v", "payload"}) {
        root = cJSON_Parse(good);
        cJSON_DeleteItemFromObject(root, key);
        assert(parse_request(root) == Request::Invalid);
        cJSON_Delete(root);
    }
    root = cJSON_Parse(good);
    cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(root, "v"), 1.5);
    assert(parse_request(root) == Request::Invalid);
    cJSON_Delete(root);
    assert(parse_request(nullptr) == Request::Other);
    root = cJSON_Parse(R"({"name":"voice.turn"})");
    assert(parse_request(root) == Request::Other);
    cJSON_Delete(root);
    std::printf("SENSOR_PROTOCOL PASS bytes=%zu capacity=%zu bounds=1 correlation=1 validation=1\n",
                std::strlen(out.data() + 1), kadence_control::FrameBytes);
}
