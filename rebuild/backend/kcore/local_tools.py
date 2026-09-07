"""Project-owned capabilities: no shell, arbitrary paths, URLs or device handles."""
from __future__ import annotations

import ast
import math
import operator
from datetime import datetime
from zoneinfo import ZoneInfo

from .context_store import ContextStore
from .tool_bridge import KadenceToolBoundary, KadenceToolSpec


def schema(properties: dict, *required: str) -> dict:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def string(maximum: int = 800, minimum: int = 1) -> dict:
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def calculate(expression: str) -> float | int:
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 40:
        raise ValueError("calculation exceeds complexity limit")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("exponent exceeds limit")
            value = binary[type(node.op)](left, right)
        else:
            raise ValueError("unsupported calculation")
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e15:
            raise ValueError("calculation outside numeric range")
        return value
    return visit(tree.body)


def make_local_tools(store: ContextStore | None, *, timezone_name: str = "Europe/London") -> KadenceToolBoundary:
    ZoneInfo(timezone_name)  # Validate owner configuration before opening runtime.

    async def clock(args):
        selected = ZoneInfo(args.get("timezone", timezone_name))
        now = datetime.now(selected)
        return {"datetime": now.isoformat(timespec="seconds"), "weekday": now.strftime("%A"),
                "timezone": str(selected), "spoken": f"{now:%A}, {now.day} {now:%B}, {now:%H:%M}"}

    async def arithmetic(args):
        return {"expression": args["expression"], "result": calculate(args["expression"])}

    specs = [
        KadenceToolSpec("clock", "Current date and time. Optional IANA timezone, e.g. Europe/London.",
                        schema({"timezone": string(64)}), clock),
        KadenceToolSpec("calculate", "Exact bounded arithmetic using numbers and + - * / % ** parentheses.",
                        schema({"expression": string(180)}, "expression"), arithmetic),
    ]
    if store is not None:
        async def remember(args): return await store.perform("add", kind="memory", **args)
        async def recall(args): return await store.perform("list", kind="memory", **args)
        async def forget(args): return await store.perform("delete", kind="memory", **args)
        async def task_add(args): return await store.perform("add", kind="task", **args)
        async def task_list(args): return await store.perform("list", kind="task", **args)
        async def task_done(args): return await store.perform("complete", kind="task", **args)
        identity = schema({"id": {"type": "integer", "minimum": 1, "maximum": 2147483647}}, "id")
        specs.extend([
            KadenceToolSpec("remember", "Save one explicitly requested note for future sessions.", schema({"text": string()}, "text"), remember, writes=True),
            KadenceToolSpec("recall", "Search saved notes by literal keyword; empty query lists recent notes.", schema({"query": string(120, 0)}), recall),
            KadenceToolSpec("forget", "Delete one saved note using its exact returned ID.", identity, forget, writes=True),
            KadenceToolSpec("task_add", "Add an item to the local to-do list. Does not schedule notifications.", schema({"text": string()}, "text"), task_add, writes=True),
            KadenceToolSpec("task_list", "Read unfinished local to-do items; optional keyword filter.", schema({"query": string(120, 0)}), task_list),
            KadenceToolSpec("task_done", "Complete one to-do item using its exact returned ID.", identity, task_done, writes=True),
        ])
    return KadenceToolBoundary(specs)
