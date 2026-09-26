# Voice latency — host 0.4.3 candidate

The target is 2–3 seconds from the end of a recording to the first spoken
answer. This is a target for warm, ordinary conversational turns, not a measured
hardware result or a deadline promised for camera/tool requests and cloud calls.
The existing 4.8-second recording window is unchanged.

## Evidence and firmware audit

The owner's `Kadence-diagnostics(9).json`, build `99d6642` / host 0.4.2,
contained these two completed turns on 2026-09-25:

| Stage | Turn 1 | Turn 2 |
| --- | ---: | ---: |
| Transcription | 2.037 s | 0.811 s |
| Reasoning | 4.055 s | 3.148 s |
| Complete speech rendering | 6.002 s | 11.753 s |

The host collected every Edge MP3 chunk, decoded the complete answer, and only
then started Windows playback and sent a length-prefixed PCM reply to the body.
For the second turn, the first encoded speech arrived roughly nine seconds
before the completed speech was available. Replacing just the LLM would leave
this full-answer wait in place.

Firmware `probe21.cpp` wraps `voice_lan.cpp` output with
`voice_playback_buffer.cpp`: received PCM is staged in PSRAM and subsequently
copied through an internal-RAM scratch buffer into the codec. This preserves
the previously repaired audio/DMA ownership contract. The 55-second response
and 15-second receive limits are timeouts, not mandatory sleeps. The short
120 ms playback drain guard cannot explain the observed 10–15-second delay.
There is no evidence that sensor polling or the recording window caused this
particular delay.

## Changes

- **Windows speaker / Bluetooth:** decode MP3 packets as they arrive in the
  isolated speech child, queue PCM on the host, and start the default Windows
  audio device after a 200 ms prebuffer. Network and codec work never runs in
  the audio device callback. The codec and resampler retain state across chunks.
- **Overlap:** privately render the first short sentence of a reply while
  Ollama completes the plan. No audio leaves that private queue until the whole
  plan has passed the existing strict validation and the accepted reply matches
  the prepared prefix. The remaining text renders while the first sentence
  plays. Tool plans never receive speech previews. This uses up to two speech
  requests per conversational answer and may introduce a sentence-boundary
  pause if the second request is slow.
- **Ollama:** opportunistically preload the selected model when the server
  starts, request a 30-minute keep-alive, retain `think:false`, remove duplicated
  persona text, and place changing clock/user context after the stable tool
  instructions. Normal answers default to one or two sentences, usually under
  40 words. Requests for detail and roleplay can still expand. The persona and
  selected model are preserved.
- **Completion:** the robot receives silence for only the remaining Windows
  playback duration. No second playback of the answer occurs. Memory and
  proposed confirmations still commit only after both device success and
  Windows completion. Cancellation kills/reaps children, discards drafts and
  stops the audio device. A failure after output starts cannot replay the full
  answer using a fallback voice.
- **Packaging:** PyAV is included for frame-based MP3 decoding. The original
  generic streaming decoder reads ahead 64 KiB (about eleven seconds at Edge's
  48 kbit/s encoding), so wrapping it in a streaming input did not solve this
  problem. PyAV's packet parser produces PCM from the first available frames.

Robot-only and Both retain the existing complete-buffer playback path and
firmware. They receive the Ollama/prompt improvements, but the early streaming
playback benefit applies to **Windows speaker / Bluetooth**. Reminders retain
their established delivery path. Firmware 0.21.6 and schema v4 are unchanged.

## Install and compare

1. Quit Kadence. Extract the entire new desktop ZIP and double-click
   `Install-Kadence.cmd`. Open the existing desktop shortcut; confirm **0.4.3**.
2. Select **Windows speaker / Bluetooth**. Windows' default output should be
   the intended laptop speaker, Bluetooth speaker or Voicemod route. Start the
   server; its saved model is warmed in the background.
3. Ask three ordinary questions, with a pause between completed answers.
   Check **Diagnostics → FIRST AUDIO**, listen for gaps/repeated words, and
   interrupt one longer reply with a touch. Then ask another question. Confirm
   it responds normally and preserves head/camera alignment.
4. Export diagnostics if the delay is still excessive. No conversation text,
   hidden thinking, speech audio or credentials are included in this export.

`FIRST AUDIO` measures end of the received recording to Windows playback start.
It includes transcription, reasoning, speech startup and output initialization;
it excludes the recording window. It is not a microphone measurement of when a
Bluetooth speaker physically becomes audible. STT, REASONING and TTS retain
their per-stage durations; TTS now means work remaining after reasoning, since
private speech rendering can overlap reasoning. These stages should not be
added together to infer first-audio time. An interrupted/failed turn may still
have a first-audio event without being a completed turn.

Additional numeric events identify `ollama_first_token`, `ollama_load`,
`ollama_prompt`, `ollama_generate` and startup `ollama_warmup`. TEST REPLY also
emits these Ollama timings and validates the same planner format without running
tools. A model appearing in REFRESH alone does not prove reply quality.

### Smaller model, if needed

Keep the installed `qwen3.5:4b` as the initial comparison. A smaller same-family
option is `qwen3.5:2b`; its response quality and tool planning need checking on
this machine. The app does not silently replace or download models.

For a one-time download, run in Windows PowerShell (any directory):

```powershell
ollama pull qwen3.5:2b
```

Stop the Kadence server, click REFRESH, select **qwen3.5:2b**, then TEST REPLY.
The choice saves automatically; restart the server. Compare several normal
questions and a reminder with the 4b model. Re-select **qwen3.5:4b** if the
smaller model loses useful personality or planning accuracy. No source editing,
firmware flashing or ongoing PowerShell launch is needed.

## Verification and acceptance

Automated checks cover real incremental MP3 decoding, arbitrary input chunk
boundaries, child-to-parent delivery before the provider can finish, bounded
PCM, late failure, cancellation/reaping, queue ordering and underruns, private
draft rejection, model warm-up/telemetry, and completion only after Windows and
device proof. The Windows package gate exercises the shipped decoder offline,
plus the established native OpenCV/worker/storage/local-speech checks.

The tone fixture first produces PCM after **576 of 24,381 encoded bytes**;
arbitrary chunk boundaries yield the same decoded audio. This verifies removal
of full-file buffering; it is not a real Edge or Bluetooth latency benchmark.
Physical voice quality, Bluetooth timing and the 2–3-second target remain to
be accepted by the owner. Camera/perception/reflex acceptance is not changed.

Primary implementation references:

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/generate
- https://ollama.com/library/qwen3.5
- https://pyav.org/docs/stable/api/codec.html
- https://pyav.org/docs/stable/api/audio.html
