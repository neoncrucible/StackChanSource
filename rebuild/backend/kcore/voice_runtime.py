from __future__ import annotations

from dataclasses import dataclass

from .interaction import AudioSink, InteractionOrchestrator, InteractionResult, TextSink
from .runtime import RuntimeBody
from .runtime_bridge import RuntimePresentationBridge
from .voice_providers import LiveVoiceProviders, VoiceProviderSettings


@dataclass(slots=True)
class VoiceTurnRuntime:
    """Compose live providers with the proven body runtime for one spoken turn.

    Audio transport remains injected: the body/control COM port is deliberately
    not used as a raw audio pipe. A3's device-audio transport can therefore be
    added without changing cognition/provider ownership or the body command lane.
    """

    body: RuntimeBody
    orchestrator: InteractionOrchestrator
    settings: VoiceProviderSettings

    @classmethod
    def bind(
        cls,
        body: RuntimeBody,
        *,
        audio_sink: AudioSink,
        text_sink: TextSink | None = None,
        settings: VoiceProviderSettings | None = None,
    ) -> "VoiceTurnRuntime":
        resolved = VoiceProviderSettings.from_env() if settings is None else settings
        providers = LiveVoiceProviders.from_settings(resolved)
        state_bridge = RuntimePresentationBridge(body)
        orchestrator = InteractionOrchestrator(
            providers.stt,
            providers.thinker,
            providers.tts,
            state_sink=state_bridge,
            audio_sink=audio_sink,
            text_sink=text_sink,
        )
        return cls(body=body, orchestrator=orchestrator, settings=resolved)

    @property
    def busy(self) -> bool:
        return self.orchestrator.busy

    async def run_pcm_turn(self, pcm: bytes, sample_rate: int = 16000) -> InteractionResult:
        return await self.orchestrator.run_turn(pcm, sample_rate)

    def cancel_current(self) -> bool:
        return self.orchestrator.cancel_current()
