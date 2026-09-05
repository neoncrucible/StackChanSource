from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.identity import KADENCE_IDENTITY
from kcore.interaction import InteractionOrchestrator


class FakeSTT:
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        assert pcm == b"voice"
        assert sample_rate == 16000
        return "What time is it?"


class AlternateThinker:
    def __init__(self) -> None:
        self.prompt = ""

    async def stream_reply(self, text: str):
        self.prompt = text
        yield "It is "
        await asyncio.sleep(0)
        yield "test o'clock."


class FakeTTS:
    async def synthesize(self, text: str):
        assert text == "It is test o'clock."
        yield b"audio-a"
        await asyncio.sleep(0)
        yield b"audio-b"


class BrokenThinker:
    async def stream_reply(self, text: str):
        if False:
            yield ""
        raise RuntimeError("forced provider failure")


class SlowSTT:
    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        await asyncio.sleep(30)
        return "never"


async def exercise_success() -> None:
    states: list[str] = []
    audio: list[bytes] = []
    streamed: list[str] = []
    thinker = AlternateThinker()

    async def state_sink(state: str) -> None:
        states.append(state)

    async def audio_sink(chunk: bytes) -> None:
        audio.append(chunk)

    async def text_sink(chunk: str) -> None:
        streamed.append(chunk)

    orchestrator = InteractionOrchestrator(
        FakeSTT(),
        thinker,
        FakeTTS(),
        state_sink=state_sink,
        audio_sink=audio_sink,
        text_sink=text_sink,
    )
    result = await orchestrator.run_turn(b"voice", 16000)

    assert KADENCE_IDENTITY.name == "Kadence"
    assert "You are Kadence" in thinker.prompt
    assert "What time is it?" in thinker.prompt
    assert result.transcript == "What time is it?"
    assert result.reply == "It is test o'clock."
    assert result.audio_bytes == len(b"audio-aaudio-b")
    assert states == ["listening", "thinking", "speaking", "idle"]
    assert b"".join(audio) == b"audio-aaudio-b"
    assert "".join(streamed) == result.reply
    assert orchestrator.busy is False


async def exercise_failure_recovery() -> None:
    states: list[str] = []

    async def state_sink(state: str) -> None:
        states.append(state)

    orchestrator = InteractionOrchestrator(
        FakeSTT(),
        BrokenThinker(),
        FakeTTS(),
        state_sink=state_sink,
    )
    try:
        await orchestrator.run_turn(b"voice", 16000)
    except RuntimeError as exc:
        assert "forced provider failure" in str(exc)
    else:
        raise AssertionError("forced provider failure did not propagate")

    assert states == ["listening", "thinking", "degraded", "idle"]
    assert orchestrator.busy is False


async def exercise_cancel() -> None:
    states: list[str] = []
    listening = asyncio.Event()

    async def state_sink(state: str) -> None:
        states.append(state)
        if state == "listening":
            listening.set()

    orchestrator = InteractionOrchestrator(
        SlowSTT(),
        AlternateThinker(),
        FakeTTS(),
        state_sink=state_sink,
    )
    task = asyncio.create_task(orchestrator.run_turn(b"voice", 16000))
    await asyncio.wait_for(listening.wait(), timeout=1.0)
    assert orchestrator.cancel_current() is True
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled interaction did not raise CancelledError")

    assert states == ["listening", "idle"]
    assert orchestrator.busy is False


async def main() -> None:
    await exercise_success()
    await exercise_failure_recovery()
    await exercise_cancel()
    print(
        "PHASE_A3_GATE PASS identity=provider-independent stream=1 audio=1 "
        "cancel=1 provider_failure=recovered single_turn=1"
    )


if __name__ == "__main__":
    asyncio.run(main())
