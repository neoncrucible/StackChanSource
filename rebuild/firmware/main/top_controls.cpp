#include "top_controls.h"
#include "top_logic.h"
#include "device_ack.h"
#include "nvs.h"
#include "esp_random.h"

namespace {
struct TopCommand { char raw[768]; };
QueueHandle_t g_top_queue=nullptr;
void (*g_top_emit)(const char*)=nullptr;
i2c_master_dev_handle_t g_top_touch=nullptr;
bool g_top_initialized=false, g_top_led_ready=false, g_top_touch_ready=false;
int g_top_brightness=18, g_top_max_volume=100;
bool g_top_quiet=false, g_top_reverse=false, g_top_sound=true;
uint64_t g_top_next_poll=0, g_top_next_led=0, g_top_save_due=0, g_top_volume_until=0;
kadence_top::Touch g_top_gesture;
kadence_top::Memory g_top_memory;

bool top_write(i2c_master_dev_handle_t device, uint8_t reg, uint8_t value) {
    const uint8_t bytes[]{reg,value};
    return device && i2c_master_transmit(device,bytes,2,15)==ESP_OK;
}
bool top_read(i2c_master_dev_handle_t device, uint8_t reg, uint8_t& value) {
    return device && i2c_master_transmit_receive(device,&reg,1,&value,1,15)==ESP_OK;
}
bool top_bit(uint8_t reg, bool set) {
    uint8_t value=0;
    return top_read(g_probe9.power_expander,reg,value) &&
        top_write(g_probe9.power_expander,reg,set?value|0x20:value&~0x20);
}
void top_save() {
    nvs_handle_t handle;
    if (nvs_open("kade_ui",NVS_READWRITE,&handle)!=ESP_OK) return;
    nvs_set_u8(handle,"volume",g_user_volume.load());
    nvs_set_u8(handle,"mute",g_user_mute.load());
    nvs_set_u8(handle,"brightness",g_top_brightness);
    nvs_set_u8(handle,"maximum",g_top_max_volume);
    nvs_set_u8(handle,"quiet",g_top_quiet);
    nvs_set_u8(handle,"reverse",g_top_reverse);
    nvs_set_u8(handle,"sound",g_top_sound);
    nvs_set_u8(handle,"best",g_top_memory.best);
    const esp_err_t result=nvs_commit(handle);
    nvs_close(handle);
    if (result!=ESP_OK) ESP_LOGW(kLogTag,"TOP settings=volatile");
}
void top_initialize() {
    g_top_initialized=true;
    nvs_handle_t handle;
    if (nvs_open("kade_ui",NVS_READONLY,&handle)==ESP_OK) {
        auto read=[&](const char* key, int fallback, int high) {
            uint8_t value=0;
            return nvs_get_u8(handle,key,&value)==ESP_OK?std::min<int>(value,high):fallback;
        };
        g_top_max_volume=read("maximum",100,100);
        g_user_volume.store(read("volume",100,g_top_max_volume));
        g_user_mute.store(read("mute",0,1));
        g_top_brightness=read("brightness",18,60);
        g_top_quiet=read("quiet",0,1); g_top_reverse=read("reverse",0,1); g_top_sound=read("sound",1,1);
        g_top_memory.best=read("best",0,24);
        nvs_close(handle);
    }
    // PY32 pin 13 only: high-byte registers, preserving servo-power pin zero.
    g_top_led_ready=top_bit(0x04,true) && top_bit(0x0c,false) && top_bit(0x0a,true) &&
        top_bit(0x14,false) && top_write(g_probe9.power_expander,0x24,12);
    i2c_device_config_t config{};
    config.dev_addr_length=I2C_ADDR_BIT_LEN_7;
    config.device_address=0x68; config.scl_speed_hz=100000;
    if (i2c_master_bus_add_device(g_control.i2c_bus,&config,&g_top_touch)==ESP_OK) {
        bool ok=true;
        for (uint8_t reg=0x0a;reg<=0x0f;++reg) ok=top_write(g_top_touch,reg,0)&&ok;
        ok=top_write(g_top_touch,0x09,0x0f)&&ok;
        ok=top_write(g_top_touch,0x09,0x07)&&ok;
        ok=top_write(g_top_touch,0x08,0x22)&&ok;
        for (uint8_t reg=0x02;reg<=0x06;++reg) ok=top_write(g_top_touch,reg,0x33)&&ok;
        g_top_touch_ready=ok;
    }
    ESP_LOGI(kLogTag,"TOP ready leds=%d touch=%d owner=presentation",g_top_led_ready,g_top_touch_ready);
}
const char* top_phase() {
    switch(g_top_memory.phase) {
        case kadence_top::Phase::Show:return "watch";
        case kadence_top::Phase::Input:return "repeat";
        case kadence_top::Phase::Won:return "won";
        case kadence_top::Phase::Lost:return "finished";
        default:return "off";
    }
}
cJSON* top_status(bool ok) {
    cJSON* p=cJSON_CreateObject();
    if (!p) return nullptr;
    cJSON_AddBoolToObject(p,"ok",ok);
    cJSON_AddNumberToObject(p,"volume",g_user_volume.load());
    cJSON_AddBoolToObject(p,"muted",g_user_mute.load());
    cJSON_AddNumberToObject(p,"maximum",g_top_max_volume);
    cJSON_AddNumberToObject(p,"brightness",g_top_brightness);
    cJSON_AddBoolToObject(p,"quiet",g_top_quiet);
    cJSON_AddBoolToObject(p,"reverse",g_top_reverse);
    cJSON_AddBoolToObject(p,"sound",g_top_sound);
    cJSON_AddBoolToObject(p,"leds",g_top_led_ready);
    cJSON_AddBoolToObject(p,"top_touch",g_top_touch_ready);
    cJSON_AddBoolToObject(p,"camera_active",g_camera_active.load());
    cJSON_AddBoolToObject(p,"media_busy",g_voice_lane_busy.load());
    cJSON_AddStringToObject(p,"presentation",presentation_state_name(presentation_requested_state()));
    cJSON_AddStringToObject(p,"game",top_phase());
    cJSON_AddNumberToObject(p,"score",g_top_memory.score);
    cJSON_AddNumberToObject(p,"best",g_top_memory.best);
    cJSON_AddNumberToObject(p,"zone",g_top_memory.lit);
    cJSON_AddNumberToObject(p,"free_heap",esp_get_free_heap_size());
    cJSON_AddNumberToObject(p,"free_psram",heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    return p;
}
void top_end_game() {
    const bool was_active=g_top_game_active.exchange(false);
    g_top_memory.stop(); g_top_note.store(-1);
    if(!was_active) return;
    presence_interaction_end(); presentation_set_state(PresentationState::Idle,"game-stop");
}
void top_process(const char* raw, uint64_t now) {
    cJSON* root=cJSON_Parse(raw);
    if (!root) return;
    const cJSON* id=cJSON_GetObjectItemCaseSensitive(root,"id");
    const cJSON* name=cJSON_GetObjectItemCaseSensitive(root,"name");
    const cJSON* p=cJSON_GetObjectItemCaseSensitive(root,"payload");
    bool ok=true;
    if (!strcmp(name->valuestring,"device.settings")) {
        int volume=g_user_volume.load(), maximum=g_top_max_volume, brightness=g_top_brightness;
        bool mute=g_user_mute.load(),quiet=g_top_quiet,reverse=g_top_reverse,sound=g_top_sound;
        auto number=[&](const char* key,int& value,int high) {
            const cJSON* item=cJSON_GetObjectItemCaseSensitive(p,key);
            if (item) { if (!cJSON_IsNumber(item)||item->valuedouble<0||item->valuedouble>high||item->valuedouble!=item->valueint) ok=false; else value=item->valueint; }
        };
        auto boolean=[&](const char* key,bool& value) {
            const cJSON* item=cJSON_GetObjectItemCaseSensitive(p,key);
            if (item) { if (!cJSON_IsBool(item)) ok=false; else value=cJSON_IsTrue(item); }
        };
        number("volume",volume,100); number("maximum",maximum,100); number("brightness",brightness,60);
        boolean("muted",mute); boolean("quiet",quiet); boolean("reverse",reverse); boolean("sound",sound);
        if (ok) {
            g_top_max_volume=maximum; g_user_volume.store(std::min(volume,maximum)); g_user_mute.store(mute);
            g_top_brightness=brightness; g_top_quiet=quiet; g_top_reverse=reverse; g_top_sound=sound;
            g_top_save_due=now+5000; g_top_volume_until=now+1800;
        }
    } else if (!strcmp(name->valuestring,"game.start")) {
        bool idle=false;
        ok=g_top_led_ready && g_top_touch_ready && g_top_brightness>0 && g_voice_lane_busy.compare_exchange_strong(idle,true);
        if (ok) {
            presence_interaction_begin();
            g_top_memory.start(now,esp_random()); g_top_game_active.store(true);
            presentation_set_state(PresentationState::Attentive,"memory-game");
            g_voice_lane_busy.store(false);
        }
    } else if (!strcmp(name->valuestring,"game.stop")) top_end_game();
    char ack[kP16FrameBytes]{};
    if (device_ack(id->valuestring,name->valuestring,top_status(ok),ack,sizeof(ack)) && g_top_emit) g_top_emit(ack);
    cJSON_Delete(root);
}
bool top_controls_route(const char* raw) {
    cJSON* root=cJSON_Parse(raw);
    if (!root) return false;
    const cJSON* name=cJSON_GetObjectItemCaseSensitive(root,"name");
    const bool ours=cJSON_IsString(name) && (!strcmp(name->valuestring,"device.status")||!strcmp(name->valuestring,"device.settings")||!strcmp(name->valuestring,"game.start")||!strcmp(name->valuestring,"game.stop"));
    if (!ours) { cJSON_Delete(root); return false; }
    const cJSON* id=cJSON_GetObjectItemCaseSensitive(root,"id");
    const cJSON* v=cJSON_GetObjectItemCaseSensitive(root,"v");
    const cJSON* kind=cJSON_GetObjectItemCaseSensitive(root,"kind");
    const cJSON* p=cJSON_GetObjectItemCaseSensitive(root,"payload");
    const bool valid=cJSON_IsString(id)&&id->valuestring[0]&&strlen(id->valuestring)<48&&cJSON_IsNumber(v)&&v->valuedouble==1&&cJSON_IsString(kind)&&!strcmp(kind->valuestring,"command")&&cJSON_IsObject(p);
    if (valid) {
        TopCommand command{};
        if (strlen(raw)<sizeof(command.raw)) {
            strcpy(command.raw,raw);
            if (g_top_queue && xQueueSend(g_top_queue,&command,0)==pdTRUE) { cJSON_Delete(root); return true; }
        }
        char ack[kP16FrameBytes]{}; cJSON* payload=cJSON_CreateObject();
        cJSON_AddBoolToObject(payload,"ok",false);
        if (device_ack(id->valuestring,name->valuestring,payload,ack,sizeof(ack))&&g_top_emit) g_top_emit(ack);
    }
    cJSON_Delete(root); return true;
}
bool top_controls_start(void (*emit)(const char*)) {
    g_top_emit=emit; g_top_queue=xQueueCreate(4,sizeof(TopCommand));
    return g_top_queue!=nullptr;
}
bool top_front_cancel() {
    if (!g_top_game_active.load()) return false;
    g_top_stop_game.store(true); voice_cancel_request(); return true;
}
void top_controls_overlay(uint16_t* pixels, uint64_t now) {
    if(!g_top_game_active.load() && now>=g_top_volume_until && !g_camera_active.load()) return;
    kadence_scene::Canvas canvas(pixels);
    canvas.box(0,204,320,36,{0,0,0});
    char line[64]{};
    if(g_camera_active.load()) snprintf(line,sizeof(line),"CAMERA ACTIVE");
    else if(g_top_game_active.load()) {
        const char* phase=g_top_memory.phase==kadence_top::Phase::Show?"WATCH":g_top_memory.phase==kadence_top::Phase::Input?"REPEAT":"FINISHED";
        snprintf(line,sizeof(line),"MEMORY %s  SCORE %d",phase,g_top_memory.score);
    } else snprintf(line,sizeof(line),g_user_mute.load()?"AUDIO MUTED":"VOLUME %d",g_user_volume.load());
    canvas.text((320-static_cast<int>(strlen(line))*4)/2,212,line,{155,235,183});
    if(g_top_game_active.load()) canvas.text(104,225,"TOUCH FACE TO STOP",{110,150,120});
}
void top_controls_tick(uint64_t now) {
    if (!g_top_queue) return;
    if (!g_top_initialized) top_initialize();
    if (g_top_stop_game.exchange(false)) top_end_game();
    TopCommand command{};
    if (xQueueReceive(g_top_queue,&command,0)==pdTRUE) top_process(command.raw,now);
    if (now>=g_top_next_poll) {
        g_top_next_poll=now+50;
        uint8_t raw=0;
        if (g_top_touch_ready && top_read(g_top_touch,0x10,raw)) {
            auto gesture=g_top_gesture.update(raw,now);
            if (g_top_game_active.load()) {
                int zone=static_cast<int>(gesture)-static_cast<int>(kadence_top::Gesture::Tap0);
                if (zone>=0 && zone<=2 && g_top_memory.phase==kadence_top::Phase::Input) {
                    g_top_memory.tap(zone,now); if(g_top_sound) g_top_note.store(zone);
                    g_top_save_due=now+5000;
                }
            } else if (gesture==kadence_top::Gesture::Forward || gesture==kadence_top::Gesture::Backward || gesture==kadence_top::Gesture::Hold) {
                if (gesture==kadence_top::Gesture::Hold) g_user_mute.store(!g_user_mute.load());
                else {
                    int delta=(gesture==kadence_top::Gesture::Forward?5:-5)*(g_top_reverse?-1:1);
                    g_user_volume.store(std::clamp(g_user_volume.load()+delta,0,g_top_max_volume));
                }
                g_top_volume_until=now+1800; g_top_save_due=now+5000;
            }
        }
    }
    const int previous=g_top_memory.lit;
    g_top_memory.tick(now);
    if (g_top_game_active.load() && g_top_memory.phase==kadence_top::Phase::Off) top_end_game();
    if(g_top_sound && g_top_memory.phase==kadence_top::Phase::Show && g_top_memory.lit>=0 && previous!=g_top_memory.lit) g_top_note.store(g_top_memory.lit);
    if (g_top_save_due && now>=g_top_save_due) {
        bool idle=false;
        if(g_voice_lane_busy.compare_exchange_strong(idle,true)) { top_save(); g_top_save_due=0; g_voice_lane_busy.store(false); }
    }
    if (!g_top_led_ready || now<g_top_next_led) return;
    g_top_next_led=now+80;
    uint8_t bytes[25]{}; bytes[0]=0x30;
    const auto state=presentation_requested_state();
    for (int i=0;i<12;++i) {
        int r=0,g=0,b=0; const int j=i%6;
        if (g_camera_active.load()) { r=240; g=100; }
        else if (g_top_game_active.load()) {
            if(g_top_memory.phase==kadence_top::Phase::Lost) r=now%600<300?180:0;
            else if(g_top_memory.phase==kadence_top::Phase::Won) g=180;
            else if(j/2==g_top_memory.lit) { const int z=j/2; r=z==0?220:10; g=z==1?220:20; b=z==2?240:10; }
            else if(g_top_memory.phase==kadence_top::Phase::Input) g=18;
        } else if (now<g_top_volume_until) { if(g_user_mute.load()) r=100; else if(j*100<g_user_volume.load()*6) g=220; }
        else if (state==PresentationState::Thinking || state==PresentationState::ToolWorking) g=j==static_cast<int>((now/140)%6)?220:12;
        else if (state==PresentationState::Listening) { g=100; b=50; }
        else if (state==PresentationState::Speaking) { g=25+g_presentation_audio_level.load()/5; }
        else if (!g_top_quiet) g=6;
        const int brightness=g_camera_active.load()?std::max(10,g_top_brightness):g_top_brightness;
        r=r*brightness/100; g=std::min(g,255)*brightness/100; b=b*brightness/100;
        const uint16_t rgb=((r&0xf8)<<8)|((g&0xfc)<<3)|(b>>3);
        bytes[1+i*2]=rgb&255; bytes[2+i*2]=rgb>>8;
    }
    if (i2c_master_transmit(g_probe9.power_expander,bytes,sizeof(bytes),15)!=ESP_OK || !top_write(g_probe9.power_expander,0x24,12|0x40)) {
        g_top_next_led=now+2000; // A missing strip never creates a tight error loop.
    }
}
}
