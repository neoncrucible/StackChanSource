from __future__ import annotations

import io
import json
import os
import wave
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any


class VoiceProviderUnavailable(RuntimeError):
    """Raised when a configured live voice provider cannot be used."""


@dataclass(frozen=True, slots=True)
class VoiceProviderSettings:
    """Environment-backed live provider configuration with no embedded secrets."""

    openai_api_key: str | None
    gemini_api_key: str | None
    stt_model: str = "gpt-transcribe"
    thinker_model: str = "gemini-3.5-flash-lite"
    tts_voice: str = "en-GB-SoniaNeural"
    tts_rate: str = "+0%"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "VoiceProviderSettings":
        values = os.environ if env is None else env
        openai_key = values.get("OPENAI_API_KEY") or None
        gemini_key = values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY") or None
        return cls(
            openai_api_key=openai_key,
            gemini_api_key=gemini_key,
            stt_model=values.get("KADENCE_STT_MODEL", "gpt-transcribe"),
            thinker_model=values.get("KADENCE_THINKER_MODEL", "gemini-3.5-flash-lite"),
            tts_voice=values.get("KADENCE_TTS_VOICE", "en-GB-SoniaNeural"),
            tts_rate=values.get("KADENCE_TTS_RATE", "+0%"),
        )

    def missing_credentials(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        return tuple(missing)


def pcm16_mono_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap signed 16-bit mono PCM in a WAV container for transcription."""
    if not isinstance(pcm, (bytes, bytearray)) or not pcm:
        raise ValueError("pcm must contain audio bytes")
    if len(pcm) % 2:
        raise ValueError("16-bit PCM byte length must be even")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))
    return output.getvalue()


def _require_httpx():
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise VoiceProviderUnavailable(
            "voice providers require the 'httpx' package; install the rebuild voice extra"
        ) from exc
    return httpx


class OpenAITranscriber:
    """File-turn STT adapter using OpenAI's audio transcription endpoint."""

    endpoint = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-transcribe",
        request_timeout: float = 30.0,
    ) -> None:
        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        self.api_key = api_key
        self.model = model
        self.request_timeout = request_timeout

    async def transcribe_file(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> str:
        """Transcribe one supported encoded audio file without decoding it locally."""
        if not self.api_key:
            raise VoiceProviderUnavailable("OPENAI_API_KEY is not configured")
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            raise ValueError("audio must contain bytes")
        if not filename.strip() or not content_type.strip():
            raise ValueError("filename and content_type are required")

        httpx = _require_httpx()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": (filename, bytes(audio), content_type)}
        data = {"model": self.model}

        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.post(self.endpoint, headers=headers, files=files, data=data)
            response.raise_for_status()
            payload = response.json()

        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("OpenAI transcription returned no text")
        return text.strip()

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        wav = pcm16_mono_to_wav(pcm, sample_rate)
        return await self.transcribe_file(
            wav,
            filename="kadence-turn.wav",
            content_type="audio/wav",
        )


class GeminiThinker:
    """Streaming Gemini Interactions adapter using cancellable SSE over HTTP."""

    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gemini-3.5-flash-lite",
        request_timeout: float = 45.0,
    ) -> None:
        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        self.api_key = api_key
        self.model = model
        self.request_timeout = request_timeout

    async def stream_reply(self, text: str) -> AsyncIterator[str]:
        prompt = text.strip()
        if not prompt:
            raise ValueError("thinker input must not be empty")
        if not self.api_key:
            raise VoiceProviderUnavailable("GEMINI_API_KEY is not configured")

        httpx = _require_httpx()
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "input": prompt,
            "stream": True,
            "generation_config": {"thinking_level": "low"},
        }

        timeout = httpx.Timeout(self.request_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.endpoint}?alt=sse",
                headers=headers,
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("Gemini returned malformed SSE JSON") from exc
                    if not isinstance(event, dict):
                        continue
                    if event.get("event_type") == "error" or "error" in event:
                        raise RuntimeError("Gemini interaction stream reported an error")
                    if event.get("event_type") != "step.delta":
                        continue
                    delta = event.get("delta")
                    if not isinstance(delta, dict) or delta.get("type") != "text":
                        continue
                    chunk = delta.get("text")
                    if isinstance(chunk, str) and chunk:
                        yield chunk


class EdgeNeuralTTS:
    """Streaming Edge neural TTS adapter using Kadence's selected voice."""

    audio_encoding = "audio/mpeg"

    def __init__(
        self,
        *,
        voice: str = "en-GB-SoniaNeural",
        rate: str = "+0%",
    ) -> None:
        if not voice.strip():
            raise ValueError("voice must not be empty")
        self.voice = voice.strip()
        self.rate = rate

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        spoken = text.strip()
        if not spoken:
            raise ValueError("tts input must not be empty")
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise VoiceProviderUnavailable(
                "voice providers require the 'edge-tts' package; install the rebuild voice extra"
            ) from exc

        communicate = edge_tts.Communicate(spoken, self.voice, rate=self.rate)
        async for event in communicate.stream():
            if not isinstance(event, dict) or event.get("type") != "audio":
                continue
            raw: Any = event.get("data")
            if isinstance(raw, (bytes, bytearray)) and raw:
                yield bytes(raw)


@dataclass(frozen=True, slots=True)
class LiveVoiceProviders:
    stt: OpenAITranscriber
    thinker: GeminiThinker
    tts: EdgeNeuralTTS

    @classmethod
    def from_settings(cls, settings: VoiceProviderSettings) -> "LiveVoiceProviders":
        return cls(
            stt=OpenAITranscriber(
                api_key=settings.openai_api_key,
                model=settings.stt_model,
            ),
            thinker=GeminiThinker(
                api_key=settings.gemini_api_key,
                model=settings.thinker_model,
            ),
            tts=EdgeNeuralTTS(
                voice=settings.tts_voice,
                rate=settings.tts_rate,
            ),
        )
