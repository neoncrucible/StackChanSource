#include "../firmware/main/gesture_sensor.h"
#include <cassert>
#include <cstdio>
using namespace kadence_sensors;
struct Fake : Bus {
    uint8_t mask=0; unsigned writes=0; bool fail=false, stuck=false;
    Result probe(uint8_t) override {return Result::Ack;}
    bool write_switch(uint8_t,uint8_t v) override {if(stuck && !v) return false; mask=v; return true;}
    bool read_switch(uint8_t,uint8_t& v) override {v=mask;return true;}
    bool register_io(uint8_t a,uint8_t reg,uint8_t* d,size_t n,bool read) override {
        assert(a==0x73 && mask==1 && n<=2);
        if(fail)return false;
        if(read && reg==0) {d[0]=0x20;d[1]=0x76;}
        else if(read && reg==0x43) {d[0]=1;d[1]=0;}
        else { assert(!read); ++writes; }
        return true;
    }
};
int main(){
    Fake b;GestureSensor g(b,0x70);Snapshot s;
    g.step(0,s); assert(g.snapshot().health==Health::Unavailable && !b.writes);
    s.hub=Health::Ready;s.channels[0].health=Health::Ready;s.channels[0].mask=1<<5;
    for(unsigned t=0;t<5000;t+=20){auto r=g.step(t,s);assert(!r.failed && !b.mask);}
    assert(g.snapshot().health==Health::Ready && g.snapshot().flags==1 && g.snapshot().event_sequence>0);
    assert(b.writes==221);
    b.fail=true;auto fault=g.step(6000,s);assert(fault.failed && fault.isolated && !b.mask);
    assert(g.snapshot().health==Health::Fault && !g.snapshot().flags);
    auto before=b.writes;g.step(7000,s);assert(before==b.writes);
    b.fail=false;b.stuck=true;fault=g.step(70000,s);assert(fault.failed && !fault.isolated);
    s.channels[0].mask=0;g.step(71000,s);assert(g.snapshot().health==Health::Unavailable);
    puts("GESTURE_SENSOR PASS identity init events isolation quarantine");
}
