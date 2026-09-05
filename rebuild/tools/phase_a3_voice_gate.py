from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.providers import SpeechToText, TextToSpeech, Thinker
from kcore.voice_providers import (
    EdgeNeuralTTS,
    GeminiThinker,
    LiveVoiceProviders,
    OpenAITranscriber,
    VoiceProviderSettings,
    pcm16_mono_to_wav,
)


VOICE_SOURCE = ROOT / "backend" / "kcore" / "voice_providers.py"
RUNTIME_SOURCE = ROOT / "backend" / "kcore" / "voice_runtime.py"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle}")


def exercise_settings() -> None:
    settings = VoiceProviderSettings.from_env({})
    assert settings.stt_model == "gpt-transcribe"
    assert settings.thinker_model == "gemini-3.5-flash-lite"
    assert settings.tts_voice == "en-GB-SoniaNeural"
    assert settings.missing_credentials() == ("OPENAI_API_KEY", "GEMINI_API_KEY")

    configured = VoiceProviderSettings.from_env(
        {
            "OPENAI_API_KEY": "test-openai",
            "GOOGLE_API_KEY": "test-google",
            "KADENCE_STT_MODEL": "stt-swap",
            "KADENCE_THINKER_MODEL": "thinker-swap",
            "KADENCE_TTS_VOICE": "voice-swap",
        }
    )
    assert configured.missing_credentials() == ()
    assert configured.stt_model == "stt-swap"
    assert configured.thinker_model == "thinker-swap"
    assert configured.tts_voice == "voice-swap"


def exercise_wav_contract() -> None:
    pcm = b"\x00\x00\x10\x00\xf0\xff\x00\x00"
    wrapped = pcm16_mono_to_wav(pcm, 16000)
    with wave.open(io.BytesIO(wrapped), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.readframes(wav.getnframes()) == pcm


def exercise_protocols() -> None:
    settings = VoiceProviderSettings(
        openai_api_key="test",
        gemini_api_key="test",
    )
    providers = LiveVoiceProviders.from_settings(settings)
    assert isinstance(providers.stt, OpenAITranscriber)
    assert isinstance(providers.thinker, GeminiThinker)
    assert isinstance(providers.tts, EdgeNeuralTTS)
    assert isinstance(providers.stt, SpeechToText)
    assert isinstance(providers.thinker, Thinker)
    assert isinstance(providers.tts, TextToSpeech)


def exercise_source_guards() -> None:
    voice = VOICE_SOURCE.read_text(encoding="utf-8")
    runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")

    require(voice, "https://api.openai.com/v1/audio/transcriptions", "OpenAI STT endpoint")
    require(voice, "gpt-transcribe", "current STT model default")
    require(voice, "https://generativelanguage.googleapis.com/v1beta/interactions", "Gemini endpoint")
    require(voice, "gemini-3.5-flash-lite", "current fast thinker default")
    require(voice, '"stream": True', "Gemini streaming request")
    require(voice, "response.aiter_lines()", "cancellable async Gemini stream")
    require(voice, "en-GB-SoniaNeural", "Kadence voice default")
    require(voice, "async for event in communicate.stream()", "streamed TTS")
    require(voice, "OPENAI_API_KEY", "OpenAI environment credential")
    require(voice, "GEMINI_API_KEY", "Gemini environment credential")

    require(runtime, "RuntimePresentationBridge(body)", "embodied state bridge")
    require(runtime, "InteractionOrchestrator(", "single interaction orchestrator")
    require(runtime, "audio_sink=audio_sink", "injected audio transport")
    require(runtime, "run_pcm_turn", "normal PCM turn entry")
    require(runtime, "not used as a raw audio pipe", "COM control/audio separation")

    for forbidden in (
        "sk-proj-",
        "AIzaSy",
        "p16_execute_pose_command",
        "serial.Serial(",
    ):
        forbid(voice + runtime, forbidden, "secret or duplicate body/audio transport")


def main() -> None:
    exercise_settings()
    exercise_wav_contract()
    exercise_protocols()
    exercise_source_guards()
    print(
        "PHASE_A3_VOICE_GATE PASS providers=3 swappable=1 pcm_contract=16k-mono-s16 "
        "streaming=1 cancellable=1 secrets=env control_audio_split=1"
    )


if __name__ == "__main__":
    main()
