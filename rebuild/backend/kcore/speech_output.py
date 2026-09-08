"""Bounded speech rendering. Neither child owns serial I/O or an audio device."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .voice_providers import VoiceProviderUnavailable

MAX_PCM = 4 * 1024 * 1024
EDGE_SECONDS = 12
LOCAL_SECONDS = 12
STAGES = frozenset({"tts_connect", "tts_audio", "tts_decode", "tts_fallback",
                    "tts_local_input", "tts_local_load", "tts_local_render", "tts_ready"})

# Static program only. Spoken text travels over stdin, never through shell code,
# arguments or a temporary file. System.Speech writes PCM to RAM, not PC speakers.
WINDOWS_SPEECH = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$output = [Console]::OpenStandardOutput()
function Report-Stage([string]$name) {
    $status = [Text.Encoding]::ASCII.GetBytes('{"stage":"' + $name + '"}' + "`n")
    $output.Write($status, 0, $status.Length); $output.Flush()
}
Report-Stage 'tts_local_input'
$encoded = [Console]::In.ReadLine()
$spoken = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))
Report-Stage 'tts_local_load'
Add-Type -AssemblyName System.Speech
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$stream = [IO.MemoryStream]::new()
try {
    try {
        $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female,
            [System.Speech.Synthesis.VoiceAge]::Adult, 0,
            [Globalization.CultureInfo]::GetCultureInfo('en-GB'))
    } catch { }
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToAudioStream($stream, $format)
    Report-Stage 'tts_local_render'
    $synth.Speak($spoken)
    $bytes = $stream.ToArray()
    if ($bytes.Length -eq 0 -or $bytes.Length -gt 4194304 -or $bytes.Length % 2) { exit 2 }
    $header = [Text.Encoding]::ASCII.GetBytes('{"pcm_bytes":' + $bytes.Length + "}`n")
    $output.Write($header, 0, $header.Length)
    $output.Write($bytes, 0, $bytes.Length)
    $output.Flush()
} finally { $synth.Dispose(); $stream.Dispose() }
"""


def child_command():
    return ([sys.executable, "--speech-child"] if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "kcore.speech_child"])


def child_environment():
    return {key: value for key, value in os.environ.items() if key.upper() not in {
        "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "KADENCE_WIFI_PASSWORD"}}


async def _render(command, payload, *, timeout, progress_sink=None):
    """Kill and reap even a wedged native decoder or websocket shutdown."""
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        env=child_environment(), limit=2048, **options))
    try:
        process = await asyncio.shield(spawning)
    except asyncio.CancelledError:
        # A touch arriving during process creation must not leave an orphan.
        with contextlib.suppress(Exception):
            process = await spawning
            if process.returncode is None: process.kill()
            await process.wait()
        raise
    try:
        async with asyncio.timeout(timeout):
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()
            for _ in range(8):
                record = json.loads(await process.stdout.readline())
                if not isinstance(record, dict): break
                if record.get("stage") in STAGES:
                    if progress_sink: await progress_sink(record["stage"])
                    continue
                size = record.get("pcm_bytes")
                if type(size) is not int or not 0 < size <= MAX_PCM or size % 2: break
                pcm = await process.stdout.readexactly(size)
                if await process.stdout.read(1) or await process.wait() != 0: break
                return pcm
        raise VoiceProviderUnavailable("Speech renderer returned an invalid result")
    except (ValueError, asyncio.IncompleteReadError, BrokenPipeError) as exc:
        raise VoiceProviderUnavailable("Speech renderer did not complete") from exc
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError): process.kill()
        await process.wait()


async def synthesize_pcm(text, *, voice, rate, progress_sink=None):
    spoken = text.strip()
    if not spoken or len(spoken) > 8000:
        raise ValueError("Speech must contain 1..8000 characters")
    try:
        pcm = await _render(child_command(), json.dumps({"text": spoken,
            "voice": voice, "rate": rate}, ensure_ascii=True).encode(),
            timeout=EDGE_SECONDS, progress_sink=progress_sink)
    except (TimeoutError, VoiceProviderUnavailable, OSError):
        # Cancellation deliberately bypasses fallback: a cancelled answer must
        # never be resurrected or committed as heard.
        if os.name != "nt": raise
        if progress_sink: await progress_sink("tts_fallback")
        pcm = await synthesize_local(spoken, progress_sink=progress_sink)
    if progress_sink: await progress_sink("tts_ready")
    return pcm


async def synthesize_local(text, *, progress_sink=None):
    if os.name != "nt": raise VoiceProviderUnavailable("Local voice requires Windows")
    if not isinstance(text, str) or not 0 < len(text) <= 8000: raise ValueError("Invalid speech length")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return await _render([str(powershell), "-NoProfile", "-NonInteractive", "-Command", WINDOWS_SPEECH],
        base64.b64encode(text.encode("utf-8"))+b"\n", timeout=LOCAL_SECONDS, progress_sink=progress_sink)
