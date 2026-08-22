from __future__ import annotations

import json
from typing import Any, Dict, Optional

from plugins_func.register import Action, ActionResponse

from core.kadence_tools import KadenceToolBoundary, KadenceToolSpec
from core.kadence_utilities import KadenceReadOnlyUtilities


_WEATHER_ICONS = {"clear", "cloud", "rain", "snow"}


class KadenceToolHandlerAdapter:
    """Adapter from Xiaozhi's function-call plumbing to the Kadence boundary."""

    kadence_safe_boundary = True

    def __init__(self, boundary: KadenceToolBoundary, logger=None):
        self.boundary = boundary
        self.logger = logger

    def get_functions(self):
        return self.boundary.get_function_descriptions()

    def current_support_functions(self):
        return self.boundary.supported_tool_names()

    def has_tool(self, tool_name: str) -> bool:
        return self.boundary.has_tool(tool_name)

    async def handle_llm_function_call(
        self, conn, function_call_data: Dict[str, Any]
    ) -> ActionResponse:
        name = function_call_data.get("name")
        arguments = function_call_data.get("arguments", {})
        result = await self.boundary.execute(name, arguments)

        if self.logger is not None:
            if result["ok"]:
                self.logger.bind(tag=__name__).info(
                    f"KADENCE TOOL: accepted name={name}"
                )
            else:
                code = result.get("error", {}).get("code", "rejected")
                self.logger.bind(tag=__name__).warning(
                    f"KADENCE TOOL: rejected name={name} code={code}"
                )

        # Trusted utility handlers may attach a private UI hint. Strip it before
        # reinjection so Luna sees only factual tool data. The only M6 side effect
        # is a fixed-enum weather icon sent over Kadence's existing versioned
        # control namespace; failure to display the icon never fails the utility.
        await self._emit_trusted_ui_hint(conn, result)

        # Always send a JSON-safe structured result back through the existing
        # generic tool-result path. The model can phrase the final spoken answer,
        # but it cannot bypass this boundary into another executor.
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        return ActionResponse(action=Action.REQLLM, result=payload)

    async def _emit_trusted_ui_hint(self, conn, result: Dict[str, Any]) -> None:
        if not result.get("ok"):
            return
        data = result.get("data")
        if not isinstance(data, dict):
            return
        hint = data.pop("_kadence_ui", None)
        if not isinstance(hint, dict):
            return

        weather_icon = hint.get("weather_icon")
        if weather_icon not in _WEATHER_ICONS:
            return

        websocket = getattr(conn, "websocket", None)
        if websocket is None:
            return
        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "kadence",
                        "version": 1,
                        "event": "weather_icon",
                        "condition": weather_icon,
                    },
                    separators=(",", ":"),
                )
            )
            if self.logger is not None:
                self.logger.bind(tag=__name__).info(
                    f"KADENCE UI: weather_icon={weather_icon}"
                )
        except Exception:
            if self.logger is not None:
                self.logger.bind(tag=__name__).warning(
                    "KADENCE UI: weather icon delivery failed safely"
                )

    async def cleanup(self):
        """Match Xiaozhi's handler lifecycle without owning external resources."""

        return None


def _m5_probe_handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "probe": "m5-boundary",
        "accepted": True,
        "code": arguments["code"],
    }


def _find_openai_settings(config: Optional[Dict[str, Any]]) -> tuple[str, str]:
    config = config or {}
    llm = config.get("LLM") or {}
    luna = llm.get("OpenAILLM") or {}
    api_key = str(luna.get("api_key") or "").strip()
    model = str(luna.get("model_name") or "gpt-5.6-luna").strip()

    if not api_key:
        asr = config.get("ASR") or {}
        realtime = asr.get("OpenaiRealtimeASR") or {}
        api_key = str(realtime.get("api_key") or "").strip()
    return api_key, model


def _build_m6_boundary(config: Optional[Dict[str, Any]]) -> KadenceToolBoundary:
    api_key, model = _find_openai_settings(config)
    utilities = KadenceReadOnlyUtilities(
        openai_api_key=api_key,
        openai_model=model,
    )

    return KadenceToolBoundary(
        [
            KadenceToolSpec(
                name="kadence_datetime",
                description=(
                    "Get the current date and time. Omit location for the Kadence "
                    "server's local time, or provide a city/place for its local time."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Optional city or place, for example Tokyo or Paris.",
                            "minLength": 1,
                            "maxLength": 96,
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
                handler=utilities.current_datetime,
            ),
            KadenceToolSpec(
                name="kadence_weather",
                description=(
                    "Get read-only weather for a named place. day_offset 0 means today, "
                    "1 tomorrow, up to 6 days ahead."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City or place to look up.",
                            "minLength": 1,
                            "maxLength": 96,
                        },
                        "day_offset": {
                            "type": "integer",
                            "description": "0 today, 1 tomorrow, up to 6 days ahead.",
                            "minimum": 0,
                            "maximum": 6,
                        },
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                handler=utilities.weather,
            ),
            KadenceToolSpec(
                name="kadence_web_lookup",
                description=(
                    "Perform a bounded factual web lookup for current or externally "
                    "verifiable information. Supply only the factual search question."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Concise factual web-search question.",
                            "minLength": 3,
                            "maxLength": 300,
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=utilities.web_lookup,
            ),
        ]
    )


def build_kadence_tool_handler(
    mode: str,
    logger=None,
    config: Optional[Dict[str, Any]] = None,
) -> KadenceToolHandlerAdapter:
    normalized = (mode or "").strip().lower()

    if normalized == "m6_readonly":
        return KadenceToolHandlerAdapter(_build_m6_boundary(config), logger=logger)

    if normalized == "m5_probe":
        boundary = KadenceToolBoundary(
            [
                KadenceToolSpec(
                    name="kadence_boundary_probe",
                    description=(
                        "Internal Kadence development probe. Use only when the user "
                        "explicitly asks to run the M5 boundary probe with a code."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Short probe code spoken by the user.",
                                "minLength": 1,
                                "maxLength": 32,
                                "pattern": "^[A-Za-z0-9_-]+$",
                            }
                        },
                        "required": ["code"],
                        "additionalProperties": False,
                    },
                    handler=_m5_probe_handler,
                )
            ]
        )
        return KadenceToolHandlerAdapter(boundary, logger=logger)

    if normalized == "off":
        return KadenceToolHandlerAdapter(KadenceToolBoundary(), logger=logger)

    raise ValueError(f"Unsupported KADENCE_TOOL_MODE: {mode}")
