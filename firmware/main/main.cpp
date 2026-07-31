/*
 * Project Kadence Beta stability runtime.
 *
 * The physically proven Alpha voice loop remains intact in main_base.inc. This
 * wrapper keeps AFE/VAD active only for an actual capture window, rather than
 * leaving the processor running while Kadence is idle, thinking or speaking.
 * The ten-second limit remains a safety cap behind the 850 ms end-of-speech
 * cutoff.
 */

#define app_main kadence_base_app_main
#include "main_base.inc"
#undef app_main

namespace {

constexpr uint32_t kAlphaVadArmDelayMs = 200;
constexpr uint32_t kAlphaEndOfSpeechSilenceMs = 850;
constexpr uint32_t kBetaFinalProcessorDrainMs = 320;

std::atomic<bool> g_alpha_vad_speaking{false};
bool g_alpha_speech_seen = false;
uint32_t g_alpha_capture_started_ms = 0;
uint32_t g_alpha_vad_armed_ms = 0;
uint32_t g_alpha_last_speech_ms = 0;

bool g_beta_voice_processor_enabled = false;
bool g_beta_processor_stop_scheduled = false;
uint32_t g_beta_processor_stop_deadline_ms = 0;

void set_beta_voice_processor(bool enable, const char* reason)
{
    if (g_audio_service == nullptr || enable == g_beta_voice_processor_enabled) {
        return;
    }

    g_audio_service->EnableVoiceProcessing(enable);
    g_beta_voice_processor_enabled = enable;
    if (!enable) {
        g_alpha_vad_speaking.store(false);
    }

    mclog::tagInfo(
        kLogTag,
        "Beta AFE processor {}: {}",
        enable ? "armed" : "parked",
        reason);
}

void cancel_beta_processor_stop()
{
    g_beta_processor_stop_scheduled = false;
    g_beta_processor_stop_deadline_ms = 0;
}

void schedule_beta_processor_stop(uint32_t now)
{
    g_beta_processor_stop_scheduled = true;
    g_beta_processor_stop_deadline_ms = now + kBetaFinalProcessorDrainMs;
    mclog::tagInfo(
        kLogTag,
        "Beta AFE processor stop scheduled after {} ms final-Opus drain",
        kBetaFinalProcessorDrainMs);
}

void service_beta_processor_stop(uint32_t now)
{
    if (!g_beta_processor_stop_scheduled ||
        !deadline_reached(now, g_beta_processor_stop_deadline_ms)) {
        return;
    }

    cancel_beta_processor_stop();
    set_beta_voice_processor(false, "final Opus frames flushed");
}

void install_alpha_audio_callbacks()
{
    if (g_audio_service == nullptr) {
        mclog::tagError(kLogTag, "cannot install Beta VAD callbacks: audio service unavailable");
        return;
    }

    AudioServiceCallbacks callbacks{};
    callbacks.on_send_queue_available = []() {
        g_voice_transport.notify_send_queue_available();
    };
    callbacks.on_wake_word_detected = [](const std::string& wake_word) {
        mclog::tagInfo(kLogTag, "wake-word callback: {}", wake_word);
        if (wake_word == "Kadence") {
            g_kadence_wake_detected.store(true);
        }
    };
    callbacks.on_vad_change = [](bool speaking) {
        g_alpha_vad_speaking.store(speaking);
    };
    g_audio_service->SetCallbacks(callbacks);

    mclog::tagInfo(
        kLogTag,
        "Beta AFE end-of-speech callback installed ({} ms silence, {} ms hard cap)",
        kAlphaEndOfSpeechSilenceMs,
        kCaptureDurationMs);
}

void reset_alpha_capture_tracking(uint32_t now)
{
    g_alpha_vad_speaking.store(false);
    g_alpha_speech_seen = false;
    g_alpha_capture_started_ms = now;
    g_alpha_vad_armed_ms = now + kAlphaVadArmDelayMs;
    g_alpha_last_speech_ms = 0;
}

void submit_alpha_voice_sample(uint32_t now, const char* reason)
{
    const uint32_t capture_ms = now - g_alpha_capture_started_ms;
    g_voice_capture_allowed.store(false);
    g_voice_transport.request_transcript();
    schedule_beta_processor_stop(now);
    g_voice_ui_runtime.state = VoiceUiState::Transcribing;
    g_voice_ui_runtime.state_deadline_ms = now + kTranscriptTimeoutMs;
    show_frame(g_listening2_dsc);
    mclog::tagInfo(
        kLogTag,
        "voice sample submitted after {} ms ({}); waiting for Faster Whisper",
        capture_ms,
        reason);
}

void update_voice_ui_alpha(uint32_t now)
{
    g_voice_transport.update();
    service_beta_processor_stop(now);

    std::string transport_error;
    if (g_voice_ui_runtime.state != VoiceUiState::Idle &&
        g_voice_ui_runtime.state != VoiceUiState::Error &&
        g_voice_transport.take_error(transport_error)) {
        cancel_beta_processor_stop();
        set_beta_voice_processor(false, "voice transport error");
        fail_voice_sequence(now, transport_error);
        return;
    }

    switch (g_voice_ui_runtime.state) {
        case VoiceUiState::CuePlaying:
            if (g_listening_cue_complete.exchange(false)) {
                g_voice_ui_runtime.state = VoiceUiState::Connecting;
                g_voice_ui_runtime.green_frame_visible = true;
                g_voice_ui_runtime.next_pulse_ms = now + kListeningPulseMs;
                g_voice_ui_runtime.state_deadline_ms =
                    now + kTransportConnectTimeoutMs;
                show_frame(g_listening2_dsc);

                if (!g_voice_transport.begin_capture()) {
                    set_beta_voice_processor(false, "capture start rejected");
                    fail_voice_sequence(now, "voice transport was already busy");
                    return;
                }

                mclog::tagInfo(
                    kLogTag,
                    "listening cue complete; using warm Windows transcript channel");
            }
            return;

        case VoiceUiState::Connecting:
            if (g_voice_transport.take_capture_started()) {
                g_voice_capture_allowed.store(true);
                g_voice_ui_runtime.state = VoiceUiState::Listening;
                g_voice_ui_runtime.state_deadline_ms = now + kCaptureDurationMs;
                reset_alpha_capture_tracking(now);
                mclog::tagInfo(
                    kLogTag,
                    "robot microphone capture gate open; AFE cutoff armed after {} ms, {} ms silence ends speech, {} ms hard limit",
                    kAlphaVadArmDelayMs,
                    kAlphaEndOfSpeechSilenceMs,
                    kCaptureDurationMs);
                return;
            }
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                set_beta_voice_processor(false, "Windows transcript connection timeout");
                fail_voice_sequence(now, "Windows transcript connection timed out");
                return;
            }
            update_listening_pulse(now);
            return;

        case VoiceUiState::Listening: {
            if (deadline_reached(now, g_alpha_vad_armed_ms)) {
                const bool speaking = g_alpha_vad_speaking.load();
                if (speaking) {
                    if (!g_alpha_speech_seen) {
                        g_alpha_speech_seen = true;
                        mclog::tagInfo(kLogTag, "AFE detected user speech");
                    }
                    g_alpha_last_speech_ms = now;
                } else if (g_alpha_speech_seen && g_alpha_last_speech_ms != 0 &&
                           deadline_reached(
                               now,
                               g_alpha_last_speech_ms + kAlphaEndOfSpeechSilenceMs)) {
                    submit_alpha_voice_sample(now, "AFE end-of-speech silence");
                    return;
                }
            }

            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                submit_alpha_voice_sample(
                    now,
                    g_alpha_speech_seen ? "ten-second safety cap" :
                                          "ten-second safety cap without detected speech");
                return;
            }

            update_listening_pulse(now);
            return;
        }

        case VoiceUiState::Transcribing: {
            std::string transcript;
            if (g_voice_transport.take_transcript(transcript)) {
                cancel_beta_processor_stop();
                set_beta_voice_processor(false, "transcript complete");
                mclog::tagInfo(
                    kLogTag,
                    "WINDOWS TRANSCRIPT: {}",
                    transcript.empty() ? "<no speech recognised>" : transcript);
                g_voice_transport.complete_session();
                restore_idle_voice_state(now);
                return;
            }
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                cancel_beta_processor_stop();
                set_beta_voice_processor(false, "Windows transcript response timeout");
                fail_voice_sequence(now, "Windows transcript response timed out");
                return;
            }
            return;
        }

        case VoiceUiState::Error:
            set_beta_voice_processor(false, "voice error state");
            if (deadline_reached(now, g_voice_ui_runtime.state_deadline_ms)) {
                restore_idle_voice_state(now);
            }
            return;

        case VoiceUiState::Idle:
        default:
            set_beta_voice_processor(false, "idle");
            return;
    }
}

bool beta_voice_sequence_ready()
{
    return g_voice_ui_runtime.state == VoiceUiState::Idle &&
           !g_listening_cue_active.load() &&
           !g_voice_transport.busy();
}

void begin_beta_listening_sequence(uint32_t now)
{
    if (!beta_voice_sequence_ready()) {
        return;
    }

    cancel_beta_processor_stop();
    set_wake_word_detection(false);
    set_beta_voice_processor(true, "listening cue warm-up");
    begin_listening_sequence(now);

    if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
        set_beta_voice_processor(false, "listening sequence did not start");
        set_wake_word_detection(true);
    }
}

}  // namespace

extern "C" void app_main(void)
{
    mclog::set_level(mclog::level_info);
    mclog::set_time_format(mclog::time_format_unix_milliseconds);
    mclog::tagInfo(
        kLogTag,
        "starting Project Kadence Beta AFE stability candidate");
    log_reset_reason();

    GetHAL().init();

    kadence_motion::restore_factory_idle_policy(GetStackChan().motion());
    g_idle_motion.initialise();
    (void)initialise_kadence_wake_word();
    install_alpha_audio_callbacks();

    initialise_eye_surface();
    initialise_head_touch_toggle();
    start_boot_audio();
    start_project_kadence_startup();

    mclog::tagInfo(
        kLogTag,
        "runtime ready; Beta capture-scoped AFE active; tap toggles idle motion; either swipe cancels voice");

    while (true) {
        const uint32_t now = GetHAL().millis();

        if (g_startup_complete.load()) {
            GetStackChan().update();

            // A swipe can restore idle and rearm wake detection inside the base
            // touch handler. Park AFE first so the two input modes never overlap.
            if (g_voice_ui_runtime.state != VoiceUiState::Idle &&
                (g_head_touch_events.load() & kTouchEventAnySwipe) != 0U) {
                cancel_beta_processor_stop();
                set_beta_voice_processor(false, "head-swipe cancellation");
            }
            process_head_touch_events(now);

            if (!g_boot_audio_active.load() && !g_network_start_requested) {
                g_network_start_requested = true;
                g_voice_transport.start_network();

                // start_network() initialises and starts the processor once. Keep
                // the transport primed, but stop AFE immediately while idle.
                g_beta_voice_processor_enabled = true;
                set_beta_voice_processor(false, "idle after transport warm-up");
            }

            if (g_kadence_wake_detected.exchange(false)) {
                begin_beta_listening_sequence(now);
            }

            if (!g_boot_audio_active.load() &&
                !g_listening_cue_active.load() &&
                g_voice_ui_runtime.state == VoiceUiState::Idle &&
                !g_voice_transport.busy() &&
                g_wake_word_service_ready &&
                !g_wake_word_detection_enabled) {
                set_beta_voice_processor(false, "before wake-word rearm");
                set_wake_word_detection(true);
            }

            if (g_voice_ui_runtime.state == VoiceUiState::Idle) {
                g_idle_motion.update();
            }
        } else {
            g_head_touch_events.exchange(0);
            g_touch_active = false;
            g_touch_swiped = false;
        }

        update_voice_ui_alpha(now);
        update_eye_state(now);
        GetHAL().feedTheDog();
        GetHAL().updateHeapStatusLog();
        GetHAL().delay(20);
    }
}
