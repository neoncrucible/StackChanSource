#pragma once
// Pure RGB565 scene. No hardware, tasks, heap allocations or provider dependency.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdio>

namespace kadence_scene {

constexpr int Width = 320;
constexpr int Height = 240;
enum class State : uint8_t { Booting, Idle, Attentive, Listening, Thinking,
                            Speaking, ToolWorking, Offline, Degraded, Fault, Recovery };

struct Colour { float r, g, b; };
constexpr Colour Ink{0, 0, 0}, Ice{112, 255, 144}, White{204, 255, 210};
constexpr Colour Dim{28, 74, 38}, Copper{249, 192, 99};

inline Colour mix(Colour a, Colour b, float t) {
    t = std::clamp(t, 0.0f, 1.0f);
    return {a.r+(b.r-a.r)*t, a.g+(b.g-a.g)*t, a.b+(b.b-a.b)*t};
}
inline uint16_t rgb(Colour c) {
    return static_cast<uint16_t>((static_cast<int>(std::clamp(c.r,0.0f,255.0f))>>3)<<11 |
                                (static_cast<int>(std::clamp(c.g,0.0f,255.0f))>>2)<<5 |
                                (static_cast<int>(std::clamp(c.b,0.0f,255.0f))>>3));
}
inline void encode_rgb565(const uint16_t* pixels, uint8_t* output, size_t count) {
    // ILI9341's SPI stream is high-byte first; ESP32's native words are not.
    for (size_t i = 0; i < count; ++i) {
        output[i * 2] = static_cast<uint8_t>(pixels[i] >> 8);
        output[i * 2 + 1] = static_cast<uint8_t>(pixels[i]);
    }
}
inline float ease(float t) { t=std::clamp(t,0.0f,1.0f); return t*t*(3-2*t); }
inline uint32_t hash(uint32_t n) { n ^= n>>16; n *= 0x7feb352dU; n ^= n>>15; n *= 0x846ca68bU; return n^(n>>16); }

class Canvas {
    uint16_t* p;
public:
    explicit Canvas(uint16_t* pixels): p(pixels) {}
    void pixel(int x,int y,Colour c) { if (x>=0 && x<Width && y>=0 && y<Height) p[y*Width+x]=rgb(c); }
    void box(int x,int y,int w,int h,Colour c) {
        const int x0=std::clamp(x,0,Width), x1=std::clamp(x+w,0,Width);
        for(int row=std::clamp(y,0,Height);row<std::clamp(y+h,0,Height);++row)
            if(x1>x0) std::fill(p+row*Width+x0,p+row*Width+x1,rgb(c));
    }
    void ellipse(float cx,float cy,float rx,float ry,Colour c) {
        if(rx<=0 || ry<=0) return;
        for(int y=static_cast<int>(cy-ry-1);y<=static_cast<int>(cy+ry+1);++y) {
            float dy=(y-cy)/ry;
            if(std::abs(dy)>1) continue;
            float half=rx*std::sqrt(1-dy*dy);
            box(static_cast<int>(cx-half),y,static_cast<int>(half*2+1),1,c);
        }
    }
    void text(int x,int y,const char* value,Colour c,int scale=1) {
        // 3x5 cap font, intentionally legible at the native display resolution.
        for(const char* ch=value;*ch;++ch,x+=4*scale) {
            uint16_t g=0;
            switch(*ch) {
                case 'A': g=0b010101111101101; break; case 'B': g=0b110101110101110; break;
                case 'C': g=0b011100100100011; break; case 'D': g=0b110101101101110; break;
                case 'E': g=0b111100110100111; break; case 'F': g=0b111100110100100; break;
                case 'G': g=0b011100101101011; break; case 'H': g=0b101101111101101; break;
                case 'I': g=0b111010010010111; break; case 'J': g=0b001001001101010; break;
                case 'K': g=0b101101110101101; break; case 'L': g=0b100100100100111; break;
                case 'M': g=0b101111111101101; break; case 'N': g=0b101111111111101; break;
                case 'O': g=0b010101101101010; break; case 'P': g=0b110101110100100; break;
                case 'Q': g=0b010101101111011; break; case 'R': g=0b110101110101101; break;
                case 'S': g=0b011100010001110; break; case 'T': g=0b111010010010010; break;
                case 'U': g=0b101101101101111; break; case 'V': g=0b101101101101010; break;
                case 'W': g=0b101101111111101; break; case 'X': g=0b101101010101101; break;
                case 'Y': g=0b101101010010010; break; case 'Z': g=0b111001010100111; break;
                case '>': g=0b100010001010100; break;
                case '0': g=0b111101101101111; break; case '1': g=0b010110010010111; break;
                case '2': g=0b110001010100111; break; case '3': g=0b110001010001110; break;
                case '4': g=0b101101111001001; break; case '5': g=0b111100110001110; break;
                case '6': g=0b011100111101111; break; case '7': g=0b111001010010010; break;
                case '8': g=0b111101111101111; break; case '9': g=0b111101111001110; break;
                case ':': g=0b000010000010000; break;
                case '.': g=0b000000000000010; break; case '/': g=0b001001010100100; break;
            }
            for(int row=0;row<5;++row) for(int col=0;col<3;++col)
                if(g & (1<<(14-row*3-col))) box(x+col*scale,y+row*scale,scale,scale,c);
        }
    }
    void line(int x0,int y0,int x1,int y1,Colour colour) {
        const int dx=std::abs(x1-x0), sx=x0<x1?1:-1;
        const int dy=-std::abs(y1-y0), sy=y0<y1?1:-1;
        int error=dx+dy;
        for (;;) {
            pixel(x0,y0,colour);
            if(x0==x1 && y0==y1) break;
            const int twice=error*2;
            if(twice>=dy) { error+=dy; x0+=sx; }
            if(twice<=dx) { error+=dx; y0+=sy; }
        }
    }
};

struct Animation {
    float level=0;
    uint64_t previous=0, entered=0;
    State last=State::Booting;

    void render(uint16_t* pixels,State state,uint64_t now,float audio_level,
                uint32_t remaining_ms=0) {
        Canvas c(pixels);
        const float dt=previous==0 ? 0.05f : std::clamp(static_cast<float>(now-previous)/1000,0.0f,0.2f);
        if(previous==0 || state!=last) { entered=now; last=state; }
        previous=now;
        const float t=static_cast<float>(now%600000)/1000;
        const bool audio=state==State::Listening || state==State::Speaking;
        const bool working=state==State::Thinking || state==State::ToolWorking;
        const bool waiting=state==State::Booting || state==State::Attentive || state==State::Recovery;
        level+=(std::clamp(audio_level,0.0f,1.0f)-level)*std::min(1.0f,dt*12);
        const Colour green{100,255,136}, bright{190,255,198}, faint{18,51,28};
        Colour accent=state==State::Offline ? Dim : green;
        if(state==State::Fault || state==State::Degraded) accent={185,225,118};
        std::fill(pixels,pixels+Width*Height,rgb(Ink));

        c.box(20,18,4,12,accent);
        c.text(32,19,"KADENCE",bright,2);
        c.box(20,41,280,1,Dim);
        constexpr const char* labels[]={"BOOT","READY","ARMING","REC","PROCESS","VOICE","TOOL","OFFLINE","RETRY","FAULT","RESET"};
        const auto index=std::min(static_cast<unsigned>(state),10U);
        const char* label=labels[index];
        c.text(298-static_cast<int>(std::strlen(label))*8,20,label,accent,2);

        // Instrument frame: chamfered corners, sparse calibration marks and one
        // signal. No eyes, mouth, skin, gradients or prerecorded animation.
        c.line(28,88,42,74,Dim); c.line(42,74,112,74,Dim);
        c.line(208,74,278,74,Dim); c.line(278,74,292,88,Dim);
        c.line(28,150,42,164,Dim); c.line(42,164,112,164,Dim);
        c.line(208,164,278,164,Dim); c.line(278,164,292,150,Dim);
        for(int x=40;x<=280;x+=20) {
            c.box(x,118,1,x%40==0?5:3,faint);
            if(x%40==0) { c.box(x,84,1,3,faint); c.box(x,153,1,3,faint); }
        }
        c.text(20,56,audio ? "AUDIO" : working ? "COMPUTE" : "SIGNAL",Dim);
        c.text(264,56,"01 / 01",Dim);

        const float amplitude=audio ? level*37 : working ? 8.0f : waiting ? 4.5f : 0.0f;
        int previous_y=120;
        for(int x=36;x<=284;++x) {
            const float u=(x-36)/248.0f;
            const float envelope=std::sin(u*3.14159265f);
            const float wave=std::sin(u*35-t*(audio?13:4))*0.66f + std::sin(u*71+t*7)*0.25f;
            const int y=120+static_cast<int>(wave*envelope*amplitude);
            if(x>36) {
                c.line(x-1,previous_y+2,x,y+2,mix(Ink,accent,0.2f));
                c.line(x-1,previous_y,x,y,accent);
                if(audio && level>0.12f) c.line(x-1,previous_y-1,x,y-1,bright);
            }
            previous_y=y;
        }
        // A moving cursor supplies quiet presence without fabricating audio.
        if(!audio) {
            const int scan=40+static_cast<int>((now/18)%240);
            c.box(scan,117,2,7,bright);
        }
        if(state==State::Idle || state==State::Offline) {
            c.line(145,108,175,108,accent);
            c.line(137,116,145,108,accent); c.line(175,108,183,116,accent);
            c.line(137,124,145,132,accent); c.line(175,132,183,124,accent);
            c.line(145,132,175,132,accent);
        }

        char detail[40]{};
        if(state==State::Listening) {
            const unsigned tenths=(remaining_ms+99)/100;
            std::snprintf(detail,sizeof(detail),"MIC OPEN   %u.%u S",tenths/10,tenths%10);
        } else if(working) {
            const unsigned elapsed=static_cast<unsigned>(std::min<uint64_t>((now-entered)/1000,999));
            std::snprintf(detail,sizeof(detail),"MIC CLOSED   %u S",elapsed);
        } else {
            const char* details[]={"INITIALISING","SYSTEM STANDBY","PREPARING AUDIO","","","AUDIO OUTPUT","","HOST DISCONNECTED","TRY AGAIN","CHECK SERVER","RETURNING TO IDLE"};
            std::snprintf(detail,sizeof(detail),"%s",details[index]);
        }
        c.text((Width-static_cast<int>(std::strlen(detail))*8)/2,180,detail,bright,2);
        c.box(20,202,280,1,Dim);
        if(state==State::Listening) {
            const int length=std::clamp(static_cast<int>(remaining_ms*280/8000),0,280);
            c.box(20,201,length,3,accent);
        } else if(working || waiting) {
            const int sweep=static_cast<int>((now/14)%248);
            c.box(20+sweep,201,32,3,accent);
        } else c.box(20,201,24,3,accent);
        const char* hint=audio || working || waiting ? "> TAP TO CANCEL" : state==State::Fault || state==State::Offline ? "> CHECK SERVER" : "> TAP TO TALK";
        c.text((Width-static_cast<int>(std::strlen(hint))*4)/2,220,hint,accent);
    }
};
} // namespace kadence_scene
