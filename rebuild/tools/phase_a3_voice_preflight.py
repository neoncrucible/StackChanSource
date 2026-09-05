from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from kcore.voice_providers import VoiceProviderSettings


def main() -> int:
    settings = VoiceProviderSettings.from_env()
    httpx_ready = importlib.util.find_spec("httpx") is not None
    edge_ready = importlib.util.find_spec("edge_tts") is not None
    missing_credentials = settings.missing_credentials()

    ready = httpx_ready and edge_ready and not missing_credentials
    missing = []
    if not httpx_ready:
        missing.append("httpx")
    if not edge_ready:
        missing.append("edge-tts")
    missing.extend(missing_credentials)

    print(
        "PHASE_A3_VOICE_PREFLIGHT "
        f"{'PASS' if ready else 'NEEDS_SETUP'} "
        f"httpx={int(httpx_ready)} edge_tts={int(edge_ready)} "
        f"openai_key={int(settings.openai_api_key is not None)} "
        f"gemini_key={int(settings.gemini_api_key is not None)} "
        f"stt={settings.stt_model} thinker={settings.thinker_model} "
        f"voice={settings.tts_voice}"
    )
    if missing:
        print("PHASE_A3_VOICE_PREFLIGHT missing=" + ",".join(missing))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
