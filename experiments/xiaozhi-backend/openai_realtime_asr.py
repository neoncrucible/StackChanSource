import asyncio
import audioop
import base64
import json
import time

import websockets

from config.logger import setup_logging
from core.handle.receiveAudioHandle import startToChat
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    """Kadence Alpha OpenAI Realtime transcription provider.

    Xiaozhi delivers decoded 16 kHz mono PCM frames. OpenAI Realtime
    transcription requires 24 kHz mono PCM16, so frames are resampled in-flight
    and appended to a warm transcription WebSocket. Kadence still owns the
    speech endpoint; listen-stop commits the already-uploaded OpenAI audio
    buffer and the completed transcript enters Xiaozhi's normal chat pipeline.
    """

    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.api_key = config.get("api_key")
        self.model = config.get("model_name", "gpt-realtime-whisper")
        self.ws_url = config.get(
            "ws_url",
            "wss://api.openai.com/v1/realtime?intent=transcription",
        )
        self.language = config.get("language", "en")
        self.noise_reduction = config.get("noise_reduction", "far_field")
        self.delete_audio_file = delete_audio_file

        if not self.api_key:
            raise ValueError("OpenAI Realtime ASR requires api_key")

        self.asr_ws = None
        self.receiver_task = None
        self.session_ready = asyncio.Event()
        self.conn = None

        self.delta_text = ""
        self.resample_state = None
        self.turn_active = False
        self.turn_started_at = 0.0
        self.commit_sent_at = 0.0
        self.first_delta_seen = False
        self.send_lock = asyncio.Lock()

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)
        self.conn = conn
        await self._ensure_connected()

    async def _ensure_connected(self):
        if self.asr_ws is not None:
            return

        self.session_ready.clear()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        self.asr_ws = await websockets.connect(
            self.ws_url,
            additional_headers=headers,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=3,
        )
        self.receiver_task = asyncio.create_task(self._receive_events())

        session_update = {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "noise_reduction": (
                            {"type": self.noise_reduction}
                            if self.noise_reduction
                            else None
                        ),
                        "transcription": {
                            "model": self.model,
                            "language": self.language,
                        },
                        "turn_detection": None,
                    }
                },
            },
        }
        await self.asr_ws.send(json.dumps(session_update))
        try:
            await asyncio.wait_for(self.session_ready.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            await self._cleanup_socket()
            raise RuntimeError(
                "OpenAI Realtime transcription session did not become ready"
            )

        logger.bind(tag=TAG).info(
            f"K2 ASR LIVE ready: model={self.model}, 16k->24k PCM"
        )

    async def receive_audio(self, conn, pcm_frame, audio_have_voice):
        # Preserve Xiaozhi's manual-mode audio snapshot for optional reporting,
        # while streaming the same PCM to OpenAI in real time.
        await super().receive_audio(conn, pcm_frame, audio_have_voice)

        if not self.turn_active:
            self.turn_active = True
            self.delta_text = ""
            self.resample_state = None
            self.turn_started_at = time.monotonic()
            self.commit_sent_at = 0.0
            self.first_delta_seen = False
            logger.bind(tag=TAG).info("K2 ASR LIVE first audio frame")

        try:
            await self._ensure_connected()
            pcm24, self.resample_state = audioop.ratecv(
                pcm_frame,
                2,
                1,
                16000,
                24000,
                self.resample_state,
            )
            event = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm24).decode("ascii"),
            }
            async with self.send_lock:
                await self.asr_ws.send(json.dumps(event))
        except Exception as e:
            logger.bind(tag=TAG).error(f"K2 ASR LIVE audio send failed: {e}")
            await self._cleanup_socket()
            raise

    async def _send_stop_request(self):
        if not self.turn_active:
            logger.bind(tag=TAG).warning(
                "K2 ASR LIVE stop received without active audio"
            )
            return

        try:
            await self._ensure_connected()
            self.commit_sent_at = time.monotonic()
            async with self.send_lock:
                await self.asr_ws.send(
                    json.dumps({"type": "input_audio_buffer.commit"})
                )
            logger.bind(tag=TAG).info("K2 ASR LIVE audio buffer committed")
        except Exception as e:
            logger.bind(tag=TAG).error(f"K2 ASR LIVE commit failed: {e}")
            await self._cleanup_socket()

    async def _receive_events(self):
        try:
            async for raw in self.asr_ws:
                event = json.loads(raw)
                event_type = event.get("type", "")

                if event_type == "session.updated":
                    self.session_ready.set()
                    continue

                if event_type == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    if delta:
                        self.delta_text += delta
                        if not self.first_delta_seen:
                            self.first_delta_seen = True
                            marker = (
                                time.monotonic() - self.commit_sent_at
                                if self.commit_sent_at
                                else time.monotonic() - self.turn_started_at
                            )
                            logger.bind(tag=TAG).info(
                                "K2 ASR LIVE first transcript delta after "
                                f"{marker:.3f}s"
                            )
                    continue

                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = (
                        event.get("transcript") or self.delta_text or ""
                    ).strip()

                    since_commit = (
                        time.monotonic() - self.commit_sent_at
                        if self.commit_sent_at
                        else 0.0
                    )
                    logger.bind(tag=TAG).info(
                        f"K2 ASR LIVE completed {since_commit:.3f}s after commit: "
                        f"{transcript}"
                    )

                    conn = self.conn
                    self.turn_active = False
                    self.resample_state = None
                    self.delta_text = ""

                    # Realtime already produced the final transcript. Do NOT call
                    # ASRProviderBase.handle_voice_stop(): that path invokes the
                    # batch speech_to_text_wrapper and would transcribe a second
                    # time. Feed the completed text directly into Xiaozhi's
                    # established STT -> LLM -> TTS conversation path.
                    if conn is not None and transcript:
                        logger.bind(tag=TAG).info(
                            f"K2 ASR LIVE -> chat: {transcript}"
                        )
                        await startToChat(conn, transcript)
                    if conn is not None:
                        conn.reset_audio_states()
                    continue

                if event_type == "error":
                    error = event.get("error", {})
                    logger.bind(tag=TAG).error(
                        "K2 ASR LIVE OpenAI error: "
                        f"{error.get('code', '')} {error.get('message', error)}"
                    )
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as e:
            logger.bind(tag=TAG).warning(
                f"K2 ASR LIVE socket closed: code={e.code} reason={e.reason}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"K2 ASR LIVE receiver failed: {e}")
        finally:
            self.session_ready.clear()
            self.asr_ws = None

    async def speech_to_text(self, opus_data, session_id, artifacts=None):
        # Required by the ASRProviderBase interface but intentionally unused for
        # Realtime turns. Completed text is dispatched directly in _receive_events.
        return "", None

    async def _cleanup_socket(self):
        ws = self.asr_ws
        task = self.receiver_task
        self.asr_ws = None
        self.receiver_task = None
        self.session_ready.clear()

        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def close(self):
        await self._cleanup_socket()
