#pragma once
#include <cstdint>

namespace kadence_touch {
// One action on a deliberate press. A held finger, brief release noise or a
// second contact in the same tap cannot turn that start into a cancellation.
class FrontTouch {
    bool candidate_ = false, pressed_ = false, locked_ = false;
    uint64_t changed_ = 0, fired_ = 0;
public:
    bool update(bool down, uint64_t now) {
        if (down != candidate_) { candidate_ = down; changed_ = now; }
        if (!candidate_) {
            if (now - changed_ >= 70) pressed_ = false;
            if (!pressed_ && (!locked_ || now - fired_ >= 300)) locked_ = false;
            return false;
        }
        if (pressed_ || locked_ || now - changed_ < 15) return false;
        pressed_ = true;
        locked_ = true;
        fired_ = now;
        return true;
    }
    bool pressed() const { return pressed_; }
};
}
