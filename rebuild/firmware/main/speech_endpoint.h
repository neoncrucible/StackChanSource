#pragma once
#include <cstdint>

namespace kadence_speech {

// The classifier runs on every retained 30 ms PCM frame. This controller never
// drops pre-roll or the final word; the caller flushes its last encoded packet.
// Silence closes a spoken turn, never silence before speech has begun.
class Endpoint {
public:
    enum class Reason { Listening, Silence, NoSpeech, Limit };
    static constexpr uint32_t FrameMs = 30;
    static constexpr uint32_t SpeechMs = 90;
    static constexpr uint32_t SilenceMs = 720;
    static constexpr uint32_t NoSpeechMs = 3000;

    explicit Endpoint(uint32_t maximum_ms) : maximum_ms_(maximum_ms) {}
    Reason feed(bool speech) {
        if (reason_ != Reason::Listening) return reason_;
        elapsed_ms_ += FrameMs;
        if (speech) {
            speech_run_ms_ += FrameMs;
            quiet_ms_ = 0;
            if (speech_run_ms_ >= SpeechMs) speech_seen_ = true;
        } else {
            speech_run_ms_ = 0;
            quiet_ms_ += FrameMs;
        }
        if (speech_seen_ && quiet_ms_ >= SilenceMs) reason_ = Reason::Silence;
        else if (!speech_seen_ && elapsed_ms_ >= NoSpeechMs) reason_ = Reason::NoSpeech;
        else if (elapsed_ms_ >= maximum_ms_) reason_ = Reason::Limit;
        return reason_;
    }
    bool finished() const { return reason_ != Reason::Listening; }
    bool speech_seen() const { return speech_seen_; }
    const char* reason() const {
        switch (reason_) {
        case Reason::Silence: return "silence";
        case Reason::NoSpeech: return "no-speech";
        case Reason::Limit: return "limit";
        default: return "listening";
        }
    }
private:
    uint32_t maximum_ms_, elapsed_ms_=0, speech_run_ms_=0, quiet_ms_=0;
    bool speech_seen_=false;
    Reason reason_=Reason::Listening;
};
}
