from __future__ import annotations

import asyncio
import math

from kadence_tools import (
    KadenceToolBoundary,
    KadenceToolSpec,
    ToolRegistrationError,
)


PROBE_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "description": "Boundary probe mode.",
            "enum": ["ping"],
        },
        "count": {
            "type": "integer",
            "description": "Small bounded repeat count.",
            "minimum": 1,
            "maximum": 3,
        },
    },
    "required": ["mode"],
    "additionalProperties": False,
}


def probe_handler(arguments):
    return {
        "mode": arguments["mode"],
        "count": arguments.get("count", 1),
        "message": "boundary-ok",
    }


async def async_probe_handler(arguments):
    await asyncio.sleep(0)
    return {"received": arguments["value"]}


def exploding_handler(_arguments):
    raise RuntimeError("secret implementation detail")


def non_json_handler(_arguments):
    return {"not_json": object()}


def nan_handler(_arguments):
    return {"value": math.nan}


def expect(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS  {label}")


async def main():
    boundary = KadenceToolBoundary(
        [
            KadenceToolSpec(
                name="kadence_boundary_probe",
                description="Deterministic internal M5 boundary probe.",
                parameters=PROBE_SCHEMA,
                handler=probe_handler,
            )
        ]
    )

    descriptions = boundary.get_function_descriptions()
    expect(len(descriptions) == 1, "only allow-listed tools are advertised")
    expect(
        descriptions[0]["function"]["name"] == "kadence_boundary_probe",
        "advertised tool name is exact",
    )
    expect(
        descriptions[0]["function"]["parameters"]["additionalProperties"] is False,
        "advertised schema is closed to extra fields",
    )

    valid = await boundary.execute(
        "kadence_boundary_probe", {"mode": "ping", "count": 2}
    )
    expect(valid["ok"] is True, "valid allow-listed call succeeds")
    expect(valid["status"] == "ok", "valid call returns structured status")
    expect(valid["data"]["message"] == "boundary-ok", "handler result is returned")

    valid_json = await boundary.execute(
        "kadence_boundary_probe", '{"mode":"ping","count":1}'
    )
    expect(valid_json["ok"] is True, "valid JSON-string arguments succeed")

    unknown = await boundary.execute("invented_pc_control", {})
    expect(unknown["ok"] is False, "invented tool fails closed")
    expect(unknown["error"]["code"] == "unknown_tool", "unknown-tool code is stable")

    malformed = await boundary.execute("kadence_boundary_probe", "{not-json")
    expect(malformed["ok"] is False, "malformed JSON fails closed")
    expect(
        malformed["error"]["code"] == "malformed_json",
        "malformed-JSON code is stable",
    )

    wrong_container = await boundary.execute("kadence_boundary_probe", ["ping"])
    expect(wrong_container["ok"] is False, "non-object arguments fail closed")

    missing = await boundary.execute("kadence_boundary_probe", {})
    expect(missing["ok"] is False, "missing required field is rejected")

    wrong_type = await boundary.execute(
        "kadence_boundary_probe", {"mode": "ping", "count": "two"}
    )
    expect(wrong_type["ok"] is False, "wrong field type is rejected")

    bad_enum = await boundary.execute(
        "kadence_boundary_probe", {"mode": "execute"}
    )
    expect(bad_enum["ok"] is False, "enum violation is rejected")

    out_of_range = await boundary.execute(
        "kadence_boundary_probe", {"mode": "ping", "count": 4}
    )
    expect(out_of_range["ok"] is False, "numeric bound violation is rejected")

    extra = await boundary.execute(
        "kadence_boundary_probe",
        {"mode": "ping", "shell": "format c:"},
    )
    expect(extra["ok"] is False, "additional property is rejected")

    collision = await boundary.execute(
        "kadence_boundary_probe",
        {"mode": "ping", "__kadence_rejected__": True},
    )
    expect(collision["ok"] is False, "internal-looking extra field cannot bypass validation")

    async_boundary = KadenceToolBoundary(
        [
            KadenceToolSpec(
                name="async_probe",
                description="Async contract probe.",
                parameters={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string", "minLength": 1, "maxLength": 8}
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                handler=async_probe_handler,
            )
        ]
    )
    async_result = await async_boundary.execute("async_probe", {"value": "hello"})
    expect(async_result["ok"] is True, "async handlers are supported safely")

    failure_boundary = KadenceToolBoundary(
        [
            KadenceToolSpec(
                name="exploding_probe",
                description="Exception containment probe.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=exploding_handler,
            )
        ]
    )
    failure = await failure_boundary.execute("exploding_probe", {})
    expect(failure["ok"] is False, "handler exception is contained")
    expect(
        failure["error"]["code"] == "execution_error",
        "handler exception returns generic execution error",
    )
    expect(
        "secret implementation detail" not in str(failure),
        "handler exception details are not leaked",
    )

    invalid_result_boundary = KadenceToolBoundary(
        [
            KadenceToolSpec(
                name="non_json_probe",
                description="JSON-safety probe.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=non_json_handler,
            ),
            KadenceToolSpec(
                name="nan_probe",
                description="NaN-safety probe.",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=nan_handler,
            ),
        ]
    )
    non_json = await invalid_result_boundary.execute("non_json_probe", {})
    expect(non_json["error"]["code"] == "invalid_result", "non-JSON result is rejected")
    nan_result = await invalid_result_boundary.execute("nan_probe", {})
    expect(nan_result["error"]["code"] == "invalid_result", "NaN result is rejected")

    empty = KadenceToolBoundary()
    expect(empty.get_function_descriptions() == [], "empty boundary advertises no capabilities")
    empty_unknown = await empty.execute("weather", {"location": "London"})
    expect(empty_unknown["ok"] is False, "unregistered future M6 utility cannot run")

    try:
        boundary.register(
            KadenceToolSpec(
                name="kadence_boundary_probe",
                description="Duplicate.",
                parameters=PROBE_SCHEMA,
                handler=probe_handler,
            )
        )
    except ToolRegistrationError:
        print("PASS  duplicate tool registration is rejected")
    else:
        raise AssertionError("duplicate tool registration was accepted")

    try:
        KadenceToolBoundary(
            [
                KadenceToolSpec(
                    name="unsafe_schema",
                    description="Unsupported-schema probe.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                        "oneOf": [],
                    },
                    handler=probe_handler,
                )
            ]
        )
    except ToolRegistrationError:
        print("PASS  unsupported schema keyword is rejected at registration")
    else:
        raise AssertionError("unsupported schema keyword was silently accepted")

    try:
        KadenceToolBoundary(
            [
                KadenceToolSpec(
                    name="open_schema",
                    description="Open-schema probe.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": True,
                    },
                    handler=probe_handler,
                )
            ]
        )
    except ToolRegistrationError:
        print("PASS  open-ended object schema is rejected at registration")
    else:
        raise AssertionError("additionalProperties=true was accepted")

    print("\nM5 SAFE TOOL BOUNDARY: PASS")


if __name__ == "__main__":
    asyncio.run(main())
