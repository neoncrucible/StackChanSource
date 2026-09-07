#include "../firmware/main/avatar_scene.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <vector>

int main(int argc, char** argv) {
    constexpr std::array<uint16_t, 3> primaries{0xf800, 0x07e0, 0x001f};
    std::array<uint8_t, 8> encoded{0xa5, 0, 0, 0, 0, 0, 0, 0x5a};
    kadence_scene::encode_rgb565(primaries.data(), encoded.data() + 1, primaries.size());
    constexpr std::array<uint8_t, 8> expected{0xa5, 0xf8, 0, 0x07, 0xe0, 0, 0x1f, 0x5a};
    assert(encoded == expected);
    constexpr size_t count=kadence_scene::Width*kadence_scene::Height;
    std::vector<uint16_t> pixels(count+2,0xa55a);
    std::set<uint64_t> scenes;
    for(int state=0;state<11;++state) {
        kadence_scene::Animation animation;
        for(uint64_t ms: {0ULL,66ULL,1000ULL,4800ULL,4860ULL,4960ULL,99999ULL,4294967300ULL}) {
            animation.render(pixels.data()+1,static_cast<kadence_scene::State>(state),ms,0.7f);
            assert(pixels.front()==0xa55a && pixels.back()==0xa55a);
            for(int y=0;y<kadence_scene::Height;++y) {
                assert(pixels[1+y*kadence_scene::Width]==0);
                assert(pixels[1+y*kadence_scene::Width+319]==0);
            }
        }
        uint64_t checksum=0;
        for(size_t i=1;i<=count;++i) checksum=checksum*31+pixels[i];
        scenes.insert(checksum);
    }
    assert(scenes.size()==11);
    if(argc>1) {
        kadence_scene::Animation animation;
        animation.render(pixels.data()+1,kadence_scene::State::Idle,2200,0);
        FILE* f=std::fopen(argv[1],"wb");
        assert(f);
        std::fprintf(f,"P6\n320 240\n255\n");
        for(size_t i=1;i<=count;++i) {
            uint16_t p=pixels[i];
            uint8_t rgb[]={static_cast<uint8_t>(((p>>11)&31)*255/31),static_cast<uint8_t>(((p>>5)&63)*255/63),static_cast<uint8_t>((p&31)*255/31)};
            std::fwrite(rgb,1,3,f);
        }
        std::fclose(f);
    }
    std::puts("AVATAR_SCENE PASS states=11 bounds=preserved native_renderer=1 wire_byte_order=verified background=solid");
}
