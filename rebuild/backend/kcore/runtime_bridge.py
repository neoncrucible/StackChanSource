from __future__ import annotations

from dataclasses import dataclass

from .runtime import RuntimeBody


@dataclass(slots=True)
class RuntimePresentationBridge:
    """Bind host interaction states to the embodied device over RuntimeBody."""

    body: RuntimeBody
    timeout: float = 3.0

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("presentation bridge timeout must be positive")

    async def set_state(self, state: str) -> None:
        await self.body.send_presentation_state(state, timeout=self.timeout)

    async def __call__(self, state: str) -> None:
        await self.set_state(state)
