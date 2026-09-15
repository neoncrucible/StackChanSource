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
    root = cJSON_Parse(good);
    cJSON_ReplaceItemInObject(root, "name", cJSON_CreateString("sensors.gesture"));
    assert(parse_request(root) == Request::Gesture);
    cJSON_Delete(root);
    GestureSnapshot gesture;
    gesture.health = Health::Ready; gesture.flags = 511;
    gesture.sequence = gesture.event_sequence = UINT32_MAX;
    char gesture_ack[kadence_control::FrameBytes]{};
    assert(device_ack("gesture-check", "sensors.gesture", gesture_payload(gesture, UINT32_MAX),
                      gesture_ack, sizeof(gesture_ack)));
    assert(std::strlen(gesture_ack) < sizeof(gesture_ack));
    root = cJSON_Parse(good);
    cJSON_ReplaceItemInObject(root, "name", cJSON_CreateString("sensors.tof"));
    assert(parse_request(root) == Request::Tof);
    cJSON_AddNumberToObject(cJSON_GetObjectItemCaseSensitive(root, "payload"), "channel", 2);
    assert(parse_request(root) == Request::Invalid);
    cJSON_Delete(root);
    TofSnapshot tof;
    tof.health = Health::Ready; tof.sequence = tof.errors = UINT32_MAX;
    tof.sampled_ms = UINT32_MAX - 10; tof.raw_status = 9;
    tof.valid = true; tof.distance_mm = 4000;
    assert(device_ack(id.c_str(), "sensors.tof", tof_payload(tof, 20), out.data() + 1, kadence_control::FrameBytes));
    assert(out.front() == 'A' && out.back() == 'Z');
    root = cJSON_Parse(out.data() + 1);
    p = cJSON_GetObjectItemCaseSensitive(root, "payload");
    assert(cJSON_GetObjectItemCaseSensitive(p, "age_ms")->valueint == 31);
    assert(cJSON_GetObjectItemCaseSensitive(p, "distance_mm")->valueint == 4000);
    cJSON_Delete(root);
    tof.valid = false; p = tof_payload(tof, 20);
    assert(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(p, "distance_mm")));
    cJSON_Delete(p);
    assert(parse_request(nullptr) == Request::Other);
    root = cJSON_Parse(R"({"name":"voice.turn"})");
    assert(parse_request(root) == Request::Other);
    cJSON_Delete(root);
    std::printf("SENSOR_PROTOCOL PASS bytes=%zu capacity=%zu bounds=1 correlation=1 validation=1\n",
                std::strlen(out.data() + 1), kadence_control::FrameBytes);
}
