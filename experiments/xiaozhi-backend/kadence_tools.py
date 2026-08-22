from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional


ToolHandler = Callable[[Dict[str, Any]], Any | Awaitable[Any]]
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SUPPORTED_COMMON = {"type", "enum", "description"}
_SUPPORTED_BY_TYPE = {
    "object": {"properties", "required", "additionalProperties"},
    "array": {"items", "minItems", "maxItems"},
    "string": {"minLength", "maxLength", "pattern"},
    "integer": {"minimum", "maximum"},
    "number": {"minimum", "maximum"},
    "boolean": set(),
    "null": set(),
}


class ToolRegistrationError(ValueError):
    pass


class ToolValidationError(ValueError):
    pass


@dataclass(frozen=True)
class KadenceToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler


class KadenceToolBoundary:
    """Project-owned, fail-closed utility registry and execution gate.

    Providers may propose calls. Only this boundary decides which names exist,
    which argument shapes are valid and which handler may execute. There is no
    fallback to Xiaozhi plugins, MCP, IoT or arbitrary Python/OS execution.
    """

    def __init__(self, specs: Optional[Iterable[KadenceToolSpec]] = None):
        self._tools: Dict[str, KadenceToolSpec] = {}
        for spec in specs or ():
            self.register(spec)

    def register(self, spec: KadenceToolSpec) -> None:
        if not isinstance(spec, KadenceToolSpec):
            raise ToolRegistrationError("spec must be a KadenceToolSpec")
        if not _TOOL_NAME_RE.fullmatch(spec.name or ""):
            raise ToolRegistrationError(
                "tool names must match ^[a-z][a-z0-9_]{0,63}$"
            )
        if spec.name in self._tools:
            raise ToolRegistrationError(f"duplicate tool name: {spec.name}")
        if not isinstance(spec.description, str) or not spec.description.strip():
            raise ToolRegistrationError("tool description must be non-empty")
        if not callable(spec.handler):
            raise ToolRegistrationError("tool handler must be callable")

        self._validate_schema_definition(spec.parameters, path="$parameters")
        if spec.parameters.get("type") != "object":
            raise ToolRegistrationError("tool parameters must use an object schema")
        if spec.parameters.get("additionalProperties") is not False:
            raise ToolRegistrationError(
                "tool parameter schemas must set additionalProperties to false"
            )

        self._tools[spec.name] = spec

    def get_function_descriptions(self) -> list[Dict[str, Any]]:
        """Return only Kadence allow-listed tools in provider-neutral format."""

        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": json.loads(json.dumps(spec.parameters)),
                },
            }
            for spec in self._tools.values()
        ]

    def supported_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def execute(self, name: Any, arguments: Any) -> Dict[str, Any]:
        """Validate and execute one call, always returning a structured result."""

        if not isinstance(name, str) or name not in self._tools:
            return self._reject(
                name if isinstance(name, str) else None,
                "unknown_tool",
                "Tool is not allow-listed.",
            )

        parsed, rejection = self._parse_arguments(name, arguments)
        if rejection is not None:
            return rejection

        spec = self._tools[name]
        try:
            self._validate_value(spec.parameters, parsed, path="$arguments")
        except ToolValidationError as exc:
            return self._reject(name, "invalid_arguments", str(exc))

        try:
            result = spec.handler(parsed)
            if inspect.isawaitable(result):
                result = await result
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError):
            return self._reject(
                name,
                "invalid_result",
                "Tool returned a result that is not JSON-safe.",
            )
        except Exception:
            return self._reject(
                name,
                "execution_error",
                "Tool execution failed safely.",
            )

        return {
            "ok": True,
            "tool": name,
            "status": "ok",
            "data": result,
            "error": None,
        }

    def _parse_arguments(
        self, name: str, arguments: Any
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return None, self._reject(
                    name,
                    "malformed_json",
                    "Tool arguments were not valid JSON.",
                )

        if not isinstance(arguments, dict):
            return None, self._reject(
                name,
                "invalid_arguments",
                "Tool arguments must be a JSON object.",
            )
        return arguments, None

    @staticmethod
    def _reject(tool: Optional[str], code: str, message: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": tool,
            "status": "rejected",
            "data": None,
            "error": {"code": code, "message": message},
        }

    def _validate_schema_definition(self, schema: Any, path: str) -> None:
        if not isinstance(schema, dict):
            raise ToolRegistrationError(f"{path} must be a schema object")

        schema_type = schema.get("type")
        if schema_type not in _SUPPORTED_BY_TYPE:
            raise ToolRegistrationError(
                f"{path}.type must be one of {sorted(_SUPPORTED_BY_TYPE)}"
            )

        allowed = _SUPPORTED_COMMON | _SUPPORTED_BY_TYPE[schema_type]
        unsupported = set(schema) - allowed
        if unsupported:
            raise ToolRegistrationError(
                f"{path} uses unsupported schema keyword(s): {sorted(unsupported)}"
            )

        if "description" in schema and not isinstance(schema["description"], str):
            raise ToolRegistrationError(f"{path}.description must be a string")

        if "enum" in schema:
            enum_values = schema["enum"]
            if not isinstance(enum_values, list) or not enum_values:
                raise ToolRegistrationError(f"{path}.enum must be a non-empty list")
            for value in enum_values:
                try:
                    self._validate_type_only(schema_type, value, path=f"{path}.enum")
                except ToolValidationError as exc:
                    raise ToolRegistrationError(str(exc)) from exc

        if schema_type == "object":
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            additional = schema.get("additionalProperties")
            if not isinstance(properties, dict):
                raise ToolRegistrationError(f"{path}.properties must be an object")
            if not isinstance(required, list) or any(
                not isinstance(item, str) for item in required
            ):
                raise ToolRegistrationError(f"{path}.required must be a string list")
            if len(required) != len(set(required)):
                raise ToolRegistrationError(f"{path}.required contains duplicates")
            missing = set(required) - set(properties)
            if missing:
                raise ToolRegistrationError(
                    f"{path}.required references unknown properties: {sorted(missing)}"
                )
            if additional is not False:
                raise ToolRegistrationError(
                    f"{path}.additionalProperties must be false"
                )
            for key, child in properties.items():
                if not isinstance(key, str) or not key:
                    raise ToolRegistrationError(
                        f"{path}.properties keys must be non-empty strings"
                    )
                self._validate_schema_definition(child, f"{path}.properties.{key}")

        elif schema_type == "array":
            if "items" not in schema:
                raise ToolRegistrationError(f"{path}.items is required for arrays")
            self._validate_schema_definition(schema["items"], f"{path}.items")
            self._validate_nonnegative_int(schema, "minItems", path)
            self._validate_nonnegative_int(schema, "maxItems", path)
            if (
                "minItems" in schema
                and "maxItems" in schema
                and schema["minItems"] > schema["maxItems"]
            ):
                raise ToolRegistrationError(f"{path} minItems exceeds maxItems")

        elif schema_type == "string":
            self._validate_nonnegative_int(schema, "minLength", path)
            self._validate_nonnegative_int(schema, "maxLength", path)
            if (
                "minLength" in schema
                and "maxLength" in schema
                and schema["minLength"] > schema["maxLength"]
            ):
                raise ToolRegistrationError(f"{path} minLength exceeds maxLength")
            if "pattern" in schema:
                if not isinstance(schema["pattern"], str):
                    raise ToolRegistrationError(f"{path}.pattern must be a string")
                try:
                    re.compile(schema["pattern"])
                except re.error as exc:
                    raise ToolRegistrationError(
                        f"{path}.pattern is invalid: {exc}"
                    ) from exc

        elif schema_type in ("integer", "number"):
            for keyword in ("minimum", "maximum"):
                if keyword in schema:
                    value = schema[keyword]
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ToolRegistrationError(
                            f"{path}.{keyword} must be numeric"
                        )
            if (
                "minimum" in schema
                and "maximum" in schema
                and schema["minimum"] > schema["maximum"]
            ):
                raise ToolRegistrationError(f"{path} minimum exceeds maximum")

    @staticmethod
    def _validate_nonnegative_int(schema: Mapping[str, Any], key: str, path: str) -> None:
        if key not in schema:
            return
        value = schema[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ToolRegistrationError(f"{path}.{key} must be a non-negative integer")

    def _validate_value(self, schema: Mapping[str, Any], value: Any, path: str) -> None:
        schema_type = schema["type"]
        self._validate_type_only(schema_type, value, path)

        if "enum" in schema and value not in schema["enum"]:
            raise ToolValidationError(f"{path} is not one of the allowed values")

        if schema_type == "object":
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    raise ToolValidationError(f"{path}.{key} is required")
            unknown = set(value) - set(properties)
            if unknown:
                raise ToolValidationError(
                    f"{path} contains unknown field(s): {sorted(unknown)}"
                )
            for key, item in value.items():
                self._validate_value(properties[key], item, f"{path}.{key}")

        elif schema_type == "array":
            if len(value) < schema.get("minItems", 0):
                raise ToolValidationError(f"{path} has too few items")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                raise ToolValidationError(f"{path} has too many items")
            for index, item in enumerate(value):
                self._validate_value(schema["items"], item, f"{path}[{index}]")

        elif schema_type == "string":
            if len(value) < schema.get("minLength", 0):
                raise ToolValidationError(f"{path} is too short")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                raise ToolValidationError(f"{path} is too long")
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                raise ToolValidationError(f"{path} does not match the required pattern")

        elif schema_type in ("integer", "number"):
            if "minimum" in schema and value < schema["minimum"]:
                raise ToolValidationError(f"{path} is below the minimum")
            if "maximum" in schema and value > schema["maximum"]:
                raise ToolValidationError(f"{path} exceeds the maximum")

    @staticmethod
    def _validate_type_only(schema_type: str, value: Any, path: str) -> None:
        valid = False
        if schema_type == "object":
            valid = isinstance(value, dict)
        elif schema_type == "array":
            valid = isinstance(value, list)
        elif schema_type == "string":
            valid = isinstance(value, str)
        elif schema_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif schema_type == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif schema_type == "boolean":
            valid = isinstance(value, bool)
        elif schema_type == "null":
            valid = value is None

        if not valid:
            raise ToolValidationError(f"{path} must be of type {schema_type}")
