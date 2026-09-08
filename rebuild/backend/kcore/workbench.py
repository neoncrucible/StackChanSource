"""Local project tools and deterministic calculations shared with the desktop."""
from __future__ import annotations

import math

from .local_tools import schema, string
from .tool_bridge import KadenceToolSpec

UNITS = {
    "mm": ("length", .001, 0), "cm": ("length", .01, 0), "m": ("length", 1, 0),
    "km": ("length", 1000, 0), "in": ("length", .0254, 0), "ft": ("length", .3048, 0),
    "g": ("mass", .001, 0), "kg": ("mass", 1, 0), "oz": ("mass", .028349523125, 0), "lb": ("mass", .45359237, 0),
    "ml": ("volume", .001, 0), "l": ("volume", 1, 0),
    "c": ("temperature", 1, 273.15), "f": ("temperature", 5/9, 255.3722222222222), "k": ("temperature", 1, 0),
    "v": ("voltage", 1, 0), "mv": ("voltage", .001, 0),
    "a": ("current", 1, 0), "ma": ("current", .001, 0), "ua": ("current", 1e-6, 0),
    "ohm": ("resistance", 1, 0), "kohm": ("resistance", 1000, 0),
    "megohm": ("resistance", 1e6, 0), "milliohm": ("resistance", .001, 0),
}


def convert(value: float, source: str, target: str) -> dict:
    if type(value) not in (float, int) or not math.isfinite(value) or abs(value) > 1e12:
        raise ValueError("value outside conversion range")
    source, target = source.casefold(), target.casefold()
    if source not in UNITS or target not in UNITS or UNITS[source][0] != UNITS[target][0]:
        raise ValueError("choose compatible units")
    _, a, b = UNITS[source]
    _, c, d = UNITS[target]
    base = value*a + b
    if UNITS[source][0] == "temperature" and base < -1e-8:
        raise ValueError("temperature below absolute zero")
    result = (base-d)/c
    return {"input": value, "from": source, "to": target, "result": float(f"{result:.12g}"),
            "spoken": f"{value:g} {source} is {result:.8g} {target}."}


def ohms_law(*, voltage=None, current=None, resistance=None) -> dict:
    values = (voltage, current, resistance)
    if sum(v is not None for v in values) != 2:
        raise ValueError("provide exactly two of volts, amperes and ohms")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 or v > 1e12 for v in values if v is not None):
        raise ValueError("inputs must be finite positive numbers")
    if voltage is None: voltage = current * resistance
    if current is None: current = voltage / resistance
    if resistance is None: resistance = voltage / current
    power = voltage * current
    if not all(math.isfinite(x) and x <= 1e15 for x in (voltage, current, resistance, power)):
        raise ValueError("calculation outside numeric range")
    return {"voltage_v": voltage, "current_a": current, "resistance_ohm": resistance, "power_w": power,
            "spoken": f"{voltage:.8g} volts, {current:.8g} amperes, {resistance:.8g} ohms; power {power:.8g} watts."}


def resistor_value(bands: list[str]) -> dict:
    colours = {name: i for i, name in enumerate(("black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white"))}
    tolerance = {"brown": 1, "red": 2, "green": .5, "blue": .25, "violet": .1, "grey": .05, "gold": 5, "silver": 10}
    if not isinstance(bands, list) or len(bands) not in (4, 5) or any(not isinstance(x, str) for x in bands):
        raise ValueError("provide four or five colour bands in reading order")
    names = [x.casefold().replace("gray", "grey") for x in bands]
    if any(x not in colours for x in names[:-2]) or names[-1] not in tolerance:
        raise ValueError("invalid digit or tolerance band")
    exponent = {**colours, "gold": -1, "silver": -2}.get(names[-2])
    if exponent is None: raise ValueError("invalid multiplier band")
    value = int("".join(str(colours[x]) for x in names[:-2])) * 10**exponent
    return {"ohms": value, "tolerance_percent": tolerance[names[-1]], "spoken": f"{value:g} ohms, plus or minus {tolerance[names[-1]]:g} percent."}


def register_workbench(tools, store):
    number = {"type": "number", "minimum": -1e12, "maximum": 1e12}
    ident = {"type": "integer", "minimum": 1, "maximum": 2147483647}
    async def conversion(args): return convert(args["value"], args["source"], args["target"])
    async def ohms(args): return ohms_law(**args)
    async def resistor(args): return resistor_value(args["bands"])
    tools.register(KadenceToolSpec("convert_units", "Convert units; supported unit codes: " + ", ".join(UNITS),
        schema({"value": number, "source": string(10), "target": string(10)}, "value", "source", "target"), conversion))
    tools.register(KadenceToolSpec("ohms_law", "Ohm's law. Supply exactly two: voltage in volts, current in amperes, resistance in ohms. Also returns power in watts.",
        schema({k: {"type": "number", "minimum": 1e-12, "maximum": 1e12} for k in ("voltage", "current", "resistance")}), ohms))
    tools.register(KadenceToolSpec("resistor_bands", "Calculate four/five-band resistor value from colour names given by the user, in reading order.",
        schema({"bands": {"type": "array", "items": string(10), "minItems": 4, "maxItems": 5}}, "bands"), resistor))
    if store is None: return
    async def projects(args): return {"items": await store.call("project_list")}
    async def create(args): return await store.call("project_add", **args)
    async def resolve_project(args):
        value=dict(args)
        if ("project" in value) == ("project_id" in value):
            raise ValueError("Supply a project name or an existing project ID.")
        if "project" in value:
            name=value.pop("project").strip().casefold()
            matches=[p for p in await store.call("project_list") if p["name"].casefold()==name]
            if len(matches)!=1: raise ValueError("Project name was not uniquely found. List projects first.")
            value["project_id"]=matches[0]["id"]
        return value
    async def note(args): return await store.call("entry_add", kind="note", **await resolve_project(args))
    async def step(args): return await store.call("entry_add", kind="step", **await resolve_project(args))
    async def entries(args): return {"items": await store.call("entry_list", **await resolve_project(args))}
    async def done(args): return {"changed": await store.call("entry_done", done=True, **args)}
    async def reminders(args): return {"items": await store.call("reminder_list")}
    specs = [
        KadenceToolSpec("project_list", "List project names and IDs. Use returned IDs for project operations.", schema({}), projects),
        KadenceToolSpec("project_create", "Create a named local lab project when requested.", schema({"name": string(80)}, "name"), create, writes=True),
        KadenceToolSpec("project_note", "Save a note in an existing project. Supply project (exact name) or project_id.", schema({"project_id": ident, "project": string(80), "text": string()}, "text"), note, writes=True),
        KadenceToolSpec("project_step", "Add a checklist step. Supply project (exact name) or project_id.", schema({"project_id": ident, "project": string(80), "text": string()}, "text"), step, writes=True),
        KadenceToolSpec("project_read", "Resume or search a project's notes/checklist. Supply project (exact name) or project_id. Done steps include done=1.", schema({"project_id": ident, "project": string(80), "query": string(120, 0)}), entries),
        KadenceToolSpec("project_step_done", "Complete a checklist step by its returned entry ID.", schema({"id": ident}, "id"), done, writes=True),
        KadenceToolSpec("reminder_list", "List actual scheduled/due reminders. Explicit 'remind me at ... to ...' requests use the local scheduler; never invent a scheduled reminder.", schema({}), reminders),
    ]
    for spec in specs: tools.register(spec)
