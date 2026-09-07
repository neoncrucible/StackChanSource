#pragma once
// Pure RGB565 scene. No hardware, tasks, heap allocations or provider dependency.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

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
            }
            for(int row=0;row<5;++row) for(int col=0;col<3;++col)
                if(g & (1<<(14-row*3-col))) box(x+col*scale,y+row*scale,scale,scale,c);
        }
    }
    void eye(float cx,float cy,float openness,float gaze_x,float gaze_y,Colour accent,float focus) {
        const float rx=49, ry=36*openness;
        // One composited pass: no erase/show alternation and no network assets.
        for(int y=static_cast<int>(cy-43);y<=static_cast<int>(cy+43);++y) {
            for(int x=static_cast<int>(cx-57);x<=static_cast<int>(cx+57);++x) {
                float dx=(x-cx)/rx, dy=(y-cy)/std::max(ry,1.5f);
                float edge=std::sqrt(dx*dx+dy*dy);
                if(edge>1.16f) continue;
                Colour c=Ink;
                if(edge>1.0f) c=mix(Ink,accent,(1.16f-edge)*1.8f);
                else if(edge>0.9f) c=mix(accent,White,0.3f+(1-edge)*2);
                else {
                    c=mix(Ink,accent,0.03f+(1-edge)*0.16f);
                    float ix=x-cx-gaze_x, iy=y-cy-gaze_y;
                    float iris=std::sqrt(ix*ix+iy*iy);
                    float radius=18+focus*4;
                    if(iris<radius+4) c=mix(c,accent,std::clamp((radius+4-iris)/4,0.0f,1.0f)*0.72f);
                    if(iris<radius) {
                        float angle=std::atan2(iy,ix);
                        float spokes=0.65f+0.22f*std::sin(angle*19+iris*0.6f);
                        c=mix(accent,White,spokes*0.3f);
                        if(iris<9) c=Ink;
                        if((ix+6)*(ix+6)+(iy+7)*(iy+7)<13) c=White;
                        if((ix-8)*(ix-8)+(iy-8)*(iy-8)<3) c=accent;
                    }
                }
                pixel(x,y,c);
            }
        }
        // Small asymmetric upper accents give the gaze expression at a distance.
        box(static_cast<int>(cx-38),static_cast<int>(cy-ry-9),26,2,mix(Ink,accent,0.65f));
    }
};

struct Animation {
    float gaze_x=0, gaze_y=0, openness=1, level=0;
    uint64_t previous=0;

    void render(uint16_t* pixels,State state,uint64_t now,float audio_level) {
        Canvas c(pixels);
        const float dt=previous==0 ? 0.066f : std::clamp(static_cast<float>(now-previous)/1000,0.0f,0.2f);
        previous=now;
        const float t=static_cast<float>(now%600000)/1000;
        const bool active=state==State::Listening || state==State::Speaking || state==State::Thinking || state==State::ToolWorking;
        const uint32_t bucket=static_cast<uint32_t>(now/4100);
        float target_x=static_cast<float>(hash(bucket)%17)-8;
        float target_y=static_cast<float>(hash(bucket+57)%7)-3;
        if(active || state==State::Attentive) { target_x=0; target_y=0; }
        if(state==State::Thinking) { target_x=9; target_y=-5; }
        gaze_x+=(target_x-gaze_x)*std::min(1.0f,dt*5);
        gaze_y+=(target_y-gaze_y)*std::min(1.0f,dt*5);
        level+=(std::clamp(audio_level,0.0f,1.0f)-level)*std::min(1.0f,dt*9);
        float target_open=state==State::Offline ? 0.38f : state==State::Thinking ? 0.64f : state==State::Attentive ? 1.13f : 1.0f;
        if(state==State::ToolWorking) target_open=0.7f;
        openness+=(target_open-openness)*std::min(1.0f,dt*6);
        const uint64_t blink_phase=now%5300;
        float blink=(blink_phase>4750 && blink_phase<4960) ? std::abs(static_cast<float>(blink_phase)-4855)/105 : 1;
        float open=std::max(0.05f,openness*ease(blink));
        Colour accent=state==State::ToolWorking ? Copper : state==State::Degraded ? Copper : state==State::Fault ? Colour{241,100,113} : Ice;
        if(state==State::Offline) accent=Dim;
        // A single exact RGB565 background value: no gradients or banding.
        std::fill(pixels, pixels+Width*Height, rgb(Ink));
        c.box(20,37,280,1,Dim);
        c.text(22,18,"KADENCE",White,2);
        if ((now / 600) % 2 == 0) c.box(81,26,7,2,Ice);
        constexpr const char* labels[]={"STARTING","READY","HERE","LISTENING","THINKING","SPEAKING","WORKING","OFFLINE","RETRY","FAULT","RECOVERING"};
        const auto index=std::min(static_cast<unsigned>(state),10U);
        const char* label=labels[index];
        const int label_x=298-static_cast<int>(std::strlen(label))*4;
        c.ellipse(static_cast<float>(label_x-8),22,2,2,accent);
        c.text(label_x,20,label,accent);
        float breathe=std::sin(t*1.7f)*1.5f;
        c.eye(91+gaze_x*0.14f,112+breathe,open,gaze_x,gaze_y,accent,state==State::Listening ? 1.0f : 0.0f);
        c.eye(229+gaze_x*0.14f,112+breathe,open,gaze_x,gaze_y,accent,state==State::Listening ? 1.0f : 0.0f);
        c.box(21,100,2,26,Dim); c.box(297,100,2,26,Dim);
        c.box(26,162,11,2,Dim); c.box(283,162,11,2,Dim);
        if(state==State::Speaking) {
            c.ellipse(160,171,15+level*10,2+level*12,accent);
            if(level>0.12f) c.ellipse(160,170,11+level*6,1+level*7,Ink);
        } else if(state==State::Thinking || state==State::ToolWorking || state==State::Booting || state==State::Recovery) {
            for(int i=0;i<3;++i) c.ellipse(148+i*12,171,2,2,mix(Dim,accent,(std::sin(t*4-i*1.2f)+1)*0.5f));
        } else {
            for(int x=-15;x<=15;++x) c.box(160+x,170-static_cast<int>(x*x/100),1,2,accent);
        }
        c.box(20,204,280,1,Dim);
        if(state==State::Listening) {
            for(int i=0;i<19;++i) {
                float envelope=1-std::abs(i-9)/10.0f;
                int h=2+static_cast<int>(level*envelope*(8+5*std::sin(t*11+i*1.9f)));
                c.box(69+i*10,191-h/2,3,h,accent);
            }
        } else if(active) {
            int x=static_cast<int>((std::sin(t*2)+1)*125);
            c.box(20+x,203,30,2,accent);
        } else c.box(151,203,18,2,mix(Dim,accent,0.5f+0.25f*std::sin(t*2)));
        const char* hint=active ? "> TOUCH TO CANCEL" : state==State::Fault ? "> CHECK HOST" : "> TOUCH TO TALK";
        c.text((Width-static_cast<int>(std::strlen(hint))*4)/2,219,hint,mix(Dim,White,0.65f));
    }
};
} // namespace kadence_scene
