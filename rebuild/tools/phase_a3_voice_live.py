from __future__ import annotations

import asyncio
import io
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.voice_providers import LiveVoiceProviders, VoiceProviderSettings


def silence_wav(*, seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    frames = max(1, int(seconds * sample_rate))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


async def verify_openai_stt_endpoint(settings: VoiceProviderSettings) -> None:
    import httpx

    assert settings.openai_api_key
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    files = {"file": ("kadence-smoke.wav", silence_wav(), "audio/wav")}
    data = {"model": settings.stt_model}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict) or "text" not in payload:
        raise RuntimeError("OpenAI transcription smoke returned an unexpected payload")


async def verify_gemini_and_tts(settings: VoiceProviderSettings) -> tuple[int, int]:
    providers = LiveVoiceProviders.from_settings(settings)

    chunks: list[str] = []
    async for chunk in providers.thinker.stream_reply(
        "Reply with exactly two words: live path"
    ):
        chunks.append(chunk)
    reply = "".join(chunks).strip()
    if not reply:
        raise RuntimeError("Gemini live smoke returned no text")

    audio_bytes = 0
    async for chunk in providers.tts.synthesize(reply):
        audio_bytes += len(chunk)
    if audio_bytes <= 0:
        raise RuntimeError("Edge TTS live smoke returned no audio")

    return len(chunks), audio_bytes


async def main() -> None:
    settings = VoiceProviderSettings.from_env()
    missing = settings.missing_credentials()
    if missing:
        raise RuntimeError("missing credentials: " + ",".join(missing))

    await verify_openai_stt_endpoint(settings)
    gemini_chunks, audio_bytes = await verify_gemini_and_tts(settings)

    print(
        "PHASE_A3_VOICE_LIVE PASS "
        f"stt_endpoint=1 gemini_stream=1 gemini_chunks={gemini_chunks} "
        f"tts=1 audio_bytes={audio_bytes}"
    )


if __name__ == "__main__":
    asyncio.run(main())
