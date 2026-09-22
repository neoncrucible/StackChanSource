"""Local model choices; discovery never downloads or changes a model."""
from __future__ import annotations

import asyncio
import json
import re

DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"


def model_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Choose a valid Ollama model name.")
    value = value.strip() or DEFAULT_OLLAMA_MODEL
    if len(value) > 160 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", value):
        raise ValueError("Choose an exact Ollama model name, without spaces (for example qwen3.5:4b).")
    return value


async def installed_models() -> list[str]:
    import httpx
    try:
        async with asyncio.timeout(4):
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                async with client.stream("GET", "http://127.0.0.1:11434/api/tags") as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 256 * 1024:
                            raise ValueError("Model list too large")
        payload = json.loads(data)
        entries = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or len(entries) > 512:
            raise ValueError("Invalid model list")
        names = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
                raise ValueError("Invalid model entry")
            names.add(model_name(entry["name"]))
        return sorted(names)
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise RuntimeError("Cannot load Ollama models. Open Ollama on this PC, then try REFRESH. Your saved selection is unchanged.") from exc
