from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from .identity import IdentityProfile, KADENCE_IDENTITY
from .providers import SpeechToText, TextToSpeech, Thinker

StateSink = Callable[[str], Awaitable[None]]
AudioSink = Callable[[bytes], Awaitable[None]]
TextSink = Callable[[str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class InteractionResult:
    transcript: str
    reply: str
    audio_bytes: int


class InteractionOrchestrator:
    """Own one voice interaction lifecycle at a time.

    Device-specific state/audio transport is injected through sinks so the
    orchestration, identity and provider choices remain independent.
    """

    def __init__(
        self,
        stt: SpeechToText,
        thinker: Thinker,
        tts: TextToSpeech,
        *,
        identity: IdentityProfile = KADENCE_IDENTITY,
        state_sink: StateSink | None = None,
        audio_sink: AudioSink | None = None,
        text_sink: TextSink | None = None,
        stt_timeout: float = 20.0,
        thinker_timeout: float = 45.0,
        tts_timeout: float = 45.0,
    ) -> None:
        if stt_timeout <= 0 or thinker_timeout <= 0 or tts_timeout <= 0:
            raise ValueError("interaction timeouts must be positive")
        self.stt = stt
        self.thinker = thinker
        self.tts = tts
        self.identity = identity
        self.state_sink = state_sink
        self.audio_sink = audio_sink
        self.text_sink = text_sink
        self.stt_timeout = stt_timeout
        self.thinker_timeout = thinker_timeout
        self.tts_timeout = tts_timeout
        self._turn_lock = asyncio.Lock()
        self._active_task: asyncio.Task[InteractionResult] | None = None

    @property
    def busy(self) -> bool:
        task = self._active_task
        return task is not None and not task.done()

    async def _set_state(self, state: str) -> None:
        if self.state_sink is not None:
            await self.state_sink(state)

    async def _emit_text(self, text: str) -> None:
        if self.text_sink is not None and text:
            await self.text_sink(text)

    async def _collect_reply(self, prompt: str) -> str:
        parts: list[str] = []

        async def consume() -> None:
            async for chunk in self.thinker.stream_reply(prompt):
                if not isinstance(chunk, str):
                    raise TypeError("Thinker yielded a non-string chunk")
                if chunk:
                    parts.append(chunk)
                    await self._emit_text(chunk)

        await asyncio.wait_for(consume(), timeout=self.thinker_timeout)
        reply = "".join(parts).strip()
        if not reply:
            raise RuntimeError("Thinker returned an empty reply")
        return reply

    async def _speak(self, text: str) -> int:
        total = 0

        async def consume() -> None:
            nonlocal total
            async for chunk in self.tts.synthesize(text):
                if not isinstance(chunk, (bytes, bytearray)):
                    raise TypeError("TextToSpeech yielded a non-bytes chunk")
                raw = bytes(chunk)
                if not raw:
                    continue
                total += len(raw)
                if self.audio_sink is not None:
                    await self.audio_sink(raw)

        await asyncio.wait_for(consume(), timeout=self.tts_timeout)
        if total == 0:
            raise RuntimeError("TextToSpeech returned no audio")
        return total

    async def run_turn(self, pcm: bytes, sample_rate: int) -> InteractionResult:
        if not isinstance(pcm, (bytes, bytearray)) or not pcm:
            raise ValueError("pcm must contain audio bytes")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")

        async with self._turn_lock:
            current = asyncio.current_task()
            if current is None:
                raise RuntimeError("interaction must run inside an asyncio task")
            self._active_task = current
            try:
                await self._set_state("listening")
                transcript = await asyncio.wait_for(
                    self.stt.transcribe(bytes(pcm), sample_rate),
                    timeout=self.stt_timeout,
                )
                transcript = transcript.strip()
                if not transcript:
                    raise RuntimeError("SpeechToText returned an empty transcript")

                await self._set_state("thinking")
                prompt = self.identity.wrap_user_text(transcript)
                reply = await self._collect_reply(prompt)

                await self._set_state("speaking")
                audio_bytes = await self._speak(reply)

                await self._set_state("idle")
                return InteractionResult(transcript, reply, audio_bytes)
            except asyncio.CancelledError:
                await self._set_state("idle")
                raise
            except Exception:
                await self._set_state("degraded")
                await self._set_state("idle")
                raise
            finally:
                if self._active_task is current:
                    self._active_task = None

    def cancel_current(self) -> bool:
        task = self._active_task
        if task is None or task.done():
            return False
        task.cancel()
        return True
