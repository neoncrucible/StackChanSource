"""Private, single-turn Sonia renderer using the approved RC1 adapter/decoder."""
from __future__ import annotations
import asyncio
import json
import sys


async def render(request, output):
    from .voice_providers import EdgeNeuralTTS
    from .voice_wire import MAX_PCM_REPLY, decode_edge_mp3_to_pcm16
    text, voice, rate = (request.get(name) for name in ("text", "voice", "rate"))
    if not isinstance(text, str) or not 0 < len(text) <= 8000: raise ValueError()
    if not isinstance(voice, str) or not 0 < len(voice) <= 100: raise ValueError()
    if not isinstance(rate, str) or not 0 < len(rate) <= 10: raise ValueError()
    def stage(value):
        output.write(json.dumps({"stage": value}).encode()+b"\n"); output.flush()
    stage("tts_connect")
    parts=[]; size=0
    async for chunk in EdgeNeuralTTS(voice=voice, rate=rate).synthesize(text):
        if not parts: stage("tts_audio")
        size += len(chunk)
        if size > MAX_PCM_REPLY: raise ValueError()
        parts.append(chunk)
    stage("tts_decode")
    pcm = decode_edge_mp3_to_pcm16(b"".join(parts))
    output.write(json.dumps({"pcm_bytes": len(pcm)}).encode()+b"\n")
    output.write(pcm); output.flush()


def main():
    try:
        raw = sys.stdin.buffer.read(100001)
        if len(raw) > 100000: return 2
        request = json.loads(raw)
        if not isinstance(request, dict) or set(request) != {"text", "voice", "rate"}: return 2
        asyncio.run(render(request, sys.stdout.buffer))
        return 0
    except Exception:
        # No provider text, credentials, transcript or reply crosses diagnostics.
        return 2


if __name__ == "__main__": raise SystemExit(main())
