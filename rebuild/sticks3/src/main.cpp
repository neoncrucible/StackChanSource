#include <M5Unified.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <mbedtls/md.h>

// Kadence Remote 1.0.1. No serial/servo/camera or model ownership on this client.
static M5Canvas screen(&M5.Display);
static bool screenReady=false;
static Preferences prefs;
static WebSocketsClient ws;
static String host,ssid,password,deviceId,key,serialLine;
static String phase="offline",camera="unavailable",notice="Pair over USB";
static bool configured=false,accepted=false,streaming=false,starting=false,held=false;
static bool consumedA=false,consumedB=false;
static uint32_t sequence=1,captureId=0,frames=0,lastPing=0,lastState=0,lastDraw=0,nextWiFi=0;
static uint32_t aDown=0,bDown=0,retryMs=1000,startSeq=0,startAt=0;
static int page=0,selection=0;
static int16_t audio[2][640];
static bool pending=false;
static unsigned recordingBuffer=0;
static const char* menu[]={"Camera","Mic / Status","Network / Status","Gyro (later)","Exit"};
static String cameraKeys[12],cameraNames[12];
static int cameraCount=0;

static void resetCapture(){
    M5.Mic.end();streaming=false;starting=false;pending=false;held=false;
}
static bool sendJson(JsonDocument& doc){
    doc["v"]=1;doc["seq"]=sequence++;
    String raw;serializeJson(doc,raw);return ws.sendTXT(raw);
}
static void disconnectSafe(const char* reason="Reconnecting..."){
    resetCapture();accepted=false;phase="offline";notice=reason;
}
static bool sendAudio(unsigned index){
    uint8_t payload[1288];
    for(unsigned i=0;i<4;++i){payload[i]=(captureId>>(24-8*i))&255;payload[i+4]=(frames>>(24-8*i))&255;}
    memcpy(payload+8,audio[index],1280);
    if(!ws.sendBIN(payload,sizeof(payload))){ws.disconnect();disconnectSafe();return false;}
    ++frames;return true;
}
static void startCapture(){
    if(!accepted||streaming||starting||phase!="idle"){notice="Wait for IDLE";return;}
    starting=true;held=true;frames=0;startSeq=sequence;startAt=millis();
    JsonDocument d;d["type"]="audio.start";
    if(!sendJson(d)){ws.disconnect();disconnectSafe();}
}
static void endCapture(){
    held=false;
    if(starting)return; // start acknowledgement will send stop without leaving capture open
    if(!streaming)return;
    if(pending){
        uint32_t until=millis()+120;
        while(M5.Mic.isRecording() && int32_t(until-millis())>0)delay(1);
        if(M5.Mic.isRecording()){ws.disconnect();disconnectSafe();return;}
        if(!sendAudio(recordingBuffer))return;
        pending=false;
    }
    M5.Mic.end();streaming=false;
    JsonDocument d;d["type"]="audio.stop";d["capture"]=captureId;d["frames"]=frames;
    sendJson(d);phase="thinking";notice="Processing";
}
static void event(WStype_t type,uint8_t* payload,size_t length){
    if(type==WStype_DISCONNECTED){disconnectSafe();return;}
    if(type==WStype_CONNECTED){accepted=false;sequence=1;lastState=millis();return;}
    if(type!=WStype_TEXT)return;
    JsonDocument d;if(deserializeJson(d,payload,length))return;
    String kind=d["type"]|"";
    if(kind=="remote.challenge"){
        String nonce=d["nonce"]|"";if(nonce.length()!=64||key.length()!=64)return;
        uint8_t secret[32],digest[32];
        for(int i=0;i<32;++i){String pair=key.substring(i*2,i*2+2);secret[i]=strtoul(pair.c_str(),nullptr,16);}
        String input="1:"+nonce+":"+deviceId;
        mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),secret,32,
            reinterpret_cast<const unsigned char*>(input.c_str()),input.length(),digest);
        char proof[65];for(int i=0;i<32;++i)sprintf(proof+2*i,"%02x",digest[i]);proof[64]=0;
        JsonDocument hello;hello["v"]=1;hello["type"]="remote.hello";hello["device"]="StickS3";
        hello["device_id"]=deviceId;hello["proof"]=proof;
        String raw;serializeJson(hello,raw);ws.sendTXT(raw);return;
    }
    if(kind=="remote.accept"){accepted=true;notice="Connected";lastState=millis();return;}
    if(!accepted)return;
    if(kind=="state.snapshot"){
        lastState=millis();phase=d["kadence_state"]|"idle";camera=d["camera_state"]|"unknown";
        cameraCount=0;
        for(JsonPair pair:d["capabilities"]["camera"].as<JsonObject>()){
            if(cameraCount==12)break;cameraKeys[cameraCount]=pair.key().c_str();cameraNames[cameraCount]=pair.value().as<String>();++cameraCount;
        }
        return;
    }
    if(kind=="remote.error"){
        notice=d["message"]|"Remote error";resetCapture();return;
    }
    if(kind=="remote.result"){
        bool ok=d["ok"]|false;
        if(!ok){notice=d["message"]|"Request rejected";if(starting||streaming)resetCapture();return;}
        if(starting && (d["seq"].as<uint32_t>()==startSeq)){
            captureId=d["capture"]|0;starting=false;streaming=true;frames=0;
            if(!held){endCapture();return;}
            auto cfg=M5.Mic.config();cfg.sample_rate=16000;M5.Mic.config(cfg);
            if(!M5.Mic.begin()){ws.disconnect();disconnectSafe("Microphone unavailable");return;}
            recordingBuffer=0;pending=M5.Mic.record(audio[recordingBuffer],640,16000,false);
            if(!pending){ws.disconnect();disconnectSafe();}
        }else if(d["message"].is<String>())notice=d["message"].as<String>();
    }
}
static void serialConfig(){
    while(Serial.available()){
        char c=Serial.read();if(c=='\r')continue;
        if(c!='\n'){if(serialLine.length()<1400)serialLine+=c;else serialLine="";continue;}
        JsonDocument d;bool valid=!deserializeJson(d,serialLine);serialLine="";if(!valid)continue;
        String type=d["type"]|"";
        if(type=="kadence.remote.probe"){
            Serial.println("{\"type\":\"kadence.remote.identity\",\"device\":\"StickS3\",\"protocol\":1,\"firmware\":\"1.0.1\"}");
        }else if(type=="kadence.remote.configure"){
            String s=d["ssid"]|"",p=d["password"]|"",h=d["host"]|"",id=d["device_id"]|"",k=d["key"]|"";
            IPAddress ip;
            if(s.isEmpty()||s.length()>32||p.length()>63||!ip.fromString(h)||id.length()!=16||k.length()!=64||d["port"].as<int>()!=8766)continue;
            // Never print secrets. One NVS record avoids half-written configurations.
            d["type"]="saved";String raw;serializeJson(d,raw);prefs.putString("config",raw);
            bool ok=prefs.getString("config","")==raw;
            JsonDocument answer;answer["type"]="kadence.remote.configured";answer["device_id"]=id;answer["ok"]=ok;
            serializeJson(answer,Serial);Serial.println();Serial.flush();
            if(ok){delay(200);ESP.restart();}
        }
    }
}
static void buttons(){
    if(M5.BtnA.wasPressed()){aDown=millis();consumedA=false;if(page==0)startCapture();}
    if(M5.BtnB.wasPressed()){bDown=millis();consumedB=false;}
    if(page!=0 && M5.BtnA.isPressed()&&!consumedA && millis()-aDown>=550){
        consumedA=true;
        if(page==1){if(selection==0){page=2;selection=0;}else if(selection==4){page=0;}else page=selection+2;}
        else if(page==2 && cameraCount && accepted){JsonDocument d;d["type"]="camera.set";d["command"]=cameraKeys[selection%cameraCount];sendJson(d);}
    }
    if(page!=0 && M5.BtnB.isPressed()&&!consumedB && millis()-bDown>=550){consumedB=true;page=page==1?0:1;selection=0;}
    if(M5.BtnA.wasReleased()){
        if(page==0)endCapture();
        else if(!consumedA){int count=page==1?5:page==2?cameraCount:1;selection=(selection+1)%max(1,count);}
    }
    if(M5.BtnB.wasReleased()&&!consumedB){
        if(page==0 && !streaming&&!starting){page=1;selection=0;}
        else if(page==1||page==2){int count=page==1?5:cameraCount;selection=(selection+max(1,count)-1)%max(1,count);}
    }
}
static void draw(){
    if(!screenReady)return;
    screen.startWrite();screen.fillScreen(TFT_BLACK);screen.setTextColor(0x87F0,TFT_BLACK);
    screen.setTextSize(1);screen.setCursor(5,4);screen.printf("KADENCE / %s",accepted?"LINKED":"OFFLINE");
    if(page==0){
        screen.setTextSize(2);screen.setCursor(5,25);screen.print(streaming?"LISTENING":phase.substring(0,15));
        screen.setTextSize(1);screen.setCursor(5,55);screen.printf("CAM %s\nRSSI %d  MIC %s",camera.c_str(),WiFi.RSSI(),streaming?"ON":"OFF");
        screen.setCursor(5,85);screen.print(notice.substring(0,36));
        screen.setCursor(5,115);screen.print("Hold A: talk   B: menu");
    }else{
        screen.setCursor(5,24);
        if(page==1){for(int i=0;i<5;++i)screen.printf("%s %s\n",i==selection?">":" ",menu[i]);}
        else if(page==2){for(int i=0;i<cameraCount;++i)screen.printf("%s %s\n",i==selection?">":" ",cameraNames[i].c_str());}
        else if(page==3){screen.printf("State: %s\nPTT: hold A on main\nNo duration cutoff",phase.c_str());}
        else if(page==4){screen.printf("WiFi: %s\nIP: %s\nHost: %s\nRSSI: %d",WiFi.status()==WL_CONNECTED?"connected":"offline",WiFi.localIP().toString().c_str(),host.c_str(),WiFi.RSSI());}
        else screen.print("Gyro control\nNot available in Remote V1");
        screen.setCursor(5,115);screen.print("A/B: next/prev  Hold B: back");
    }
    screen.endWrite();
    // Clear and text rendering happen off-screen; the LCD receives one full frame.
    screen.pushSprite(0,0);
}
void setup(){
    auto cfg=M5.config();M5.begin(cfg);M5.Speaker.end();M5.Mic.end();
    M5.Display.setRotation(1);Serial.begin(115200);prefs.begin("kadence-remote",false);
    screen.setColorDepth(16);
    screenReady=screen.createSprite(M5.Display.width(),M5.Display.height())!=nullptr;
    if(!screenReady){
        M5.Display.fillScreen(TFT_BLACK);M5.Display.setCursor(5,5);
        M5.Display.print("Display buffer unavailable");
    }
    JsonDocument d;if(!deserializeJson(d,prefs.getString("config",""))){
        ssid=d["ssid"]|"";password=d["password"]|"";host=d["host"]|"";deviceId=d["device_id"]|"";key=d["key"]|"";
        configured=!ssid.isEmpty()&&host.length()>0&&key.length()==64&&deviceId.length()==16;
    }
    if(configured){
        WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.setAutoReconnect(true);WiFi.begin(ssid.c_str(),password.c_str());
        ws.begin(host.c_str(),8766,"/kadence/v1","");ws.setExtraHeaders("");ws.onEvent(event);ws.setReconnectInterval(2000);ws.enableHeartbeat(5000,3000,2);
        notice="Connecting...";
    }
}
void loop(){
    M5.update();serialConfig();
    if(configured){
        if(WiFi.status()==WL_CONNECTED){ws.loop();retryMs=1000;}
        else if(int32_t(millis()-nextWiFi)>=0){disconnectSafe();WiFi.reconnect();nextWiFi=millis()+retryMs;retryMs=min(15000u,retryMs*2);}
    }
    if(accepted && millis()-lastState>3000){ws.disconnect();disconnectSafe();}
    if(starting && millis()-startAt>3000){ws.disconnect();disconnectSafe();}
    buttons();
    if(streaming && pending && !M5.Mic.isRecording()){
        unsigned ready=recordingBuffer;recordingBuffer^=1;
        pending=M5.Mic.record(audio[recordingBuffer],640,16000,false);
        if(!pending||!sendAudio(ready)){ws.disconnect();disconnectSafe();}
    }
    if(accepted && millis()-lastPing>1000){lastPing=millis();JsonDocument d;d["type"]="remote.ping";d["rssi"]=WiFi.RSSI();sendJson(d);}
    if(millis()-lastDraw>250){lastDraw=millis();draw();}
    delay(1);
}
