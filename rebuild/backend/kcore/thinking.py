"""Bounded planner replies and safe thinking-service status."""
from __future__ import annotations

import asyncio
import json

PLAN_TIMEOUT = 22.0  # Fits the existing 52 s host / 55 s device voice deadlines.
MAX_PLAN_CHARS = 8192
PLAN_FORMAT = {
    "anyOf": [
        {"type": "object", "properties": {"reply": {"type": "string", "minLength": 1, "maxLength": 1200}},
         "required": ["reply"], "additionalProperties": False},
        {"type": "object", "properties": {
            "tool": {"type": "string", "minLength": 1, "maxLength": 64},
            "arguments": {"type": "object"}},
         "required": ["tool", "arguments"], "additionalProperties": False},
    ]
}
THINKING_REASONS = frozenset({
    "unavailable", "timeout", "model_missing", "http_error", "model_error",
    "invalid_response", "empty_response", "truncated_response", "response_limit", "invalid_plan",
})


class ThinkingServiceError(RuntimeError):
    """Only fixed codes and an optional HTTP status may leave the adapter."""

    def __init__(self, reason: str, *, http_status: int | None = None):
        self.reason = reason if reason in THINKING_REASONS else "unavailable"
        self.http_status = http_status if type(http_status) is int and 400 <= http_status <= 599 else None
        super().__init__(self.reason)


def issue_data(thinker, error: ThinkingServiceError) -> dict:
    provider = getattr(thinker, "provider", "unknown")
    data = {"stage": "providers", "provider_stage": "reasoning",
            "provider": provider if provider in {"ollama", "gemini"} else "unknown",
            "reason": error.reason}
    if error.http_status is not None:
        data["http_status"] = error.http_status
    return data


def failure_message(reason: str, provider: str = "unknown") -> str:
    service = "Ollama" if provider == "ollama" else "The thinking service"
    hints = {
        "unavailable": f"{service} could not be reached. Open it on this PC and try TEST REPLY." if provider == "ollama" else "The thinking service could not be reached. Check its connection and credentials.",
        "timeout": f"{service} did not finish within 22 seconds. The model may still be loading or too slow for voice turns.",
        "model_missing": "Ollama could not find the selected model. REFRESH and choose an installed model, then restart the server.",
        "http_error": f"{service} rejected the reply request. The HTTP status is in Diagnostics.",
        "model_error": f"{service} could not run the model. Check Ollama's own error, then try TEST REPLY." if provider == "ollama" else "The thinking service reported a model error.",
        "invalid_response": f"{service} returned an invalid response stream.",
        "empty_response": f"{service} finished without an answer.",
        "truncated_response": f"{service} reached its output limit before completing the answer.",
        "response_limit": f"{service} exceeded Kadence's reply-size limit.",
        "invalid_plan": f"{service} replied, but Kadence could not read the reply format.",
    }
    return hints.get(reason, hints["unavailable"])


def spoken_failure(reason: str, provider: str) -> str:
    if reason in {"invalid_plan", "invalid_response", "empty_response", "truncated_response", "response_limit"}:
        return "My thinking service replied, but I couldn't read a complete answer. I've recorded the problem in Diagnostics."
    if reason == "timeout":
        return "My thinking service took too long to answer. I've recorded the timeout in Diagnostics."
    if reason == "model_missing":
        return "Ollama couldn't find my selected model. Please check the model selection on the PC."
    if reason in {"model_error", "http_error"}:
        return "My thinking service couldn't complete the request. I've recorded the problem in Diagnostics."
    return "I couldn't connect to Ollama on the PC. My local notes, list and clock are still here." if provider == "ollama" else "I'm having trouble reaching my thinking service. My local notes, list and clock are still here."


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate planner key")
        result[key] = value
    return result


async def request_plan(thinker, prompt: str) -> dict:
    """Request exactly one plan; never repair or execute model output here."""
    try:
        chunks = []
        length = 0
        stream = getattr(thinker, "stream_plan", thinker.stream_reply)
        async with asyncio.timeout(PLAN_TIMEOUT):
            iterator = stream(prompt)
            try:
                async for chunk in iterator:
                    if not isinstance(chunk, str):
                        raise ThinkingServiceError("invalid_response")
                    length += len(chunk)
                    if length > MAX_PLAN_CHARS:
                        raise ThinkingServiceError("response_limit")
                    chunks.append(chunk)
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
    except asyncio.CancelledError:
        raise
    except ThinkingServiceError:
        raise
    except TimeoutError:
        raise ThinkingServiceError("timeout") from None
    except Exception:
        raise ThinkingServiceError("unavailable") from None
    raw = "".join(chunks).strip()
    if not raw:
        raise ThinkingServiceError("empty_response")
    if raw.startswith("```json\n") and raw.endswith("```"):
        raw = raw[8:-3].strip()
    try:
        plan = json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, RecursionError):
        raise ThinkingServiceError("invalid_plan") from None
    if isinstance(plan, dict):
        if set(plan) == {"reply"} and isinstance(plan["reply"], str) and plan["reply"].strip():
            return plan
        if (set(plan) == {"tool", "arguments"} and isinstance(plan["tool"], str)
                and isinstance(plan["arguments"], dict)):
            return plan
    raise ThinkingServiceError("invalid_plan")
