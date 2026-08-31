from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class SpeechToText(Protocol):
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str: ...


@runtime_checkable
class Thinker(Protocol):
    async def stream_reply(self, text: str) -> AsyncIterator[str]: ...


@runtime_checkable
class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


@runtime_checkable
class ToolBridge(Protocol):
    async def invoke(self, name: str, arguments: dict) -> dict: ...
