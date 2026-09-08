#include "../firmware/main/control_frame.h"
#include "../firmware/main/device_status_payload.h"
#include "../firmware/main/device_ack.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>

int main() {
    kadence_status::Snapshot state;
    state.volume=state.maximum=100; state.brightness=60;
    state.presentation="tool-working"; state.game="finished"; state.firmware="0.21.1";
    state.free_heap=state.free_psram=state.touch_seq=UINT32_MAX;
    state.capture_remaining_ms=8000;
    std::array<char,kadence_control::FrameBytes+2> output{};
    output.front()='A'; output.back()='Z';
    const char* id="0123456789abcdef0123456789abcdef0123456789abcde\"";
    // The actual production status builder reproduces RC2's dropped reply.
    assert(!device_ack(id,"device.status",kadence_status::payload(state,true),output.data()+1,384));
    assert(device_ack(id,"device.status",kadence_status::payload(state,true),output.data()+1,kadence_control::FrameBytes));
    assert(output.front()=='A' && output.back()=='Z');
    cJSON* parsed=cJSON_Parse(output.data()+1);
    assert(parsed);
    assert(!std::strcmp(cJSON_GetObjectItemCaseSensitive(parsed,"id")->valuestring,id));
    const cJSON* p=cJSON_GetObjectItemCaseSensitive(parsed,"payload");
    assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(p,"ok")));
    assert(cJSON_GetObjectItemCaseSensitive(p,"capture_remaining_ms")->valueint==8000);
    assert(cJSON_GetObjectItemCaseSensitive(p,"touch_seq")->valuedouble==UINT32_MAX);
    cJSON_Delete(parsed);
    std::printf("CONTROL_FRAME PASS status_bytes=%zu capacity=%zu correlation=1 escaped_id=1 bounds=1\n",std::strlen(output.data()+1),kadence_control::FrameBytes);
}
