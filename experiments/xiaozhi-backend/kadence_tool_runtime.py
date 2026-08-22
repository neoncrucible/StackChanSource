from __future__ import annotations

import json
from typing import Any, Dict

from plugins_func.register import Action, ActionResponse

from core.kadence_tools import KadenceToolBoundary, KadenceToolSpec


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
        self, _conn, function_call_data: Dict[str, Any]
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

        # Always send a JSON-safe structured result back through the existing
        # generic tool-result path. The model can phrase the final spoken answer,
        # but it cannot bypass this boundary into another executor.
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        return ActionResponse(action=Action.REQLLM, result=payload)


def _m5_probe_handler(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "probe": "m5-boundary",
        "accepted": True,
        "code": arguments["code"],
    }


def build_kadence_tool_handler(mode: str, logger=None) -> KadenceToolHandlerAdapter:
    normalized = (mode or "").strip().lower()

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
