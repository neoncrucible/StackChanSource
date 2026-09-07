from __future__ import annotations

import asyncio
import json
import math
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from kcore.companion import Companion
from kcore.context_store import ContextStore
from kcore.integrations import register_integrations
from kcore.local_tools import calculate, make_local_tools, schema
from kcore.tool_bridge import KadenceToolBoundary, KadenceToolSpec, ToolRegistrationError
from kcore.voice_wire import read_wire_turn


class Thinker:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def stream_reply(self, text):
        self.prompts.append(text)
        if isinstance(self.response, Exception):
            raise self.response
        yield json.dumps(self.response)


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def handler(args): return {"value": args.get("value", 3)}
        self.spec = KadenceToolSpec("probe", "test", schema({"value": {"type": "integer", "minimum": 0, "maximum": 5}}, "value"), handler)
        self.tools = KadenceToolBoundary([self.spec])

    async def asyncTearDown(self):
        await self.tools.close()

    async def test_allowlist_and_strict_arguments(self):
        for name, args in [("shell", {}), ([], {}), ("probe", {"value": True}), ("probe", {"value": math.nan}),
                           ("probe", {"value": 2, "confirmed": True}), ("probe", {}), ("probe", "{}"),
                           ("probe", {"value": 9}), ("probe", {"value": "2"})]:
            with self.subTest(name=name, args=args):
                self.assertFalse((await self.tools.invoke(name, args))["ok"])
        self.assertEqual((await self.tools.invoke("probe", {"value": 3}))["data"], {"value": 3})

    async def test_schema_copies_and_duplicate_rejection(self):
        self.spec.parameters["required"].clear()
        self.assertFalse((await self.tools.invoke("probe", {}))["ok"])
        advertised = self.tools.get_function_descriptions()
        advertised[0]["function"]["parameters"]["additionalProperties"] = True
        self.assertFalse((await self.tools.invoke("probe", {"value": 3, "extra": 1}))["ok"])
        with self.assertRaises(ToolRegistrationError): self.tools.register(self.spec)
        with self.assertRaises(ToolRegistrationError):
            self.tools.register(KadenceToolSpec("sync", "blocks", schema({}), lambda args: {}))

    async def test_write_denied_without_runtime_confirmation(self):
        self.tools.register(KadenceToolSpec("write", "change", schema({}), self.spec.handler, writes=True))
        self.assertEqual((await self.tools.invoke("write", {}))["error"]["code"], "denied")
        self.assertFalse((await self.tools.execute("write", {}, confirmed="yes"))["ok"])
        self.assertTrue((await self.tools.execute("write", {}, confirmed=True))["ok"])

    async def test_timeout_does_not_wait_for_cancel_resistant_handler(self):
        release = asyncio.Event()
        cancelled = asyncio.Event()
        async def stubborn(args):
            try: await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            return {}
        self.tools.register(KadenceToolSpec("hang", "hang", schema({}), stubborn, timeout=0.02))
        start = time.monotonic()
        result = await self.tools.invoke("hang", {})
        self.assertLess(time.monotonic() - start, 0.2)
        self.assertEqual(result["error"]["code"], "timeout")
        await asyncio.wait_for(cancelled.wait(), .2)
        self.assertTrue((await self.tools.invoke("probe", {"value": 1}))["ok"])
        release.set()
        await asyncio.sleep(0)

    async def test_parent_cancel_reaches_handler(self):
        started, ended = asyncio.Event(), asyncio.Event()
        async def wait(args):
            started.set()
            try: await asyncio.Event().wait()
            finally: ended.set()
        self.tools.register(KadenceToolSpec("wait", "wait", schema({}), wait))
        task = asyncio.create_task(self.tools.invoke("wait", {}))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        await asyncio.wait_for(ended.wait(), .2)

    async def test_failures_and_invalid_results_are_contained(self):
        async def broken(args): raise RuntimeError("SECRET credential in exception")
        async def invalid(args): return {"a": float("nan")}
        async def huge(args): return {"a": "x" * 20000}
        for name, handler in [("broken", broken), ("invalid", invalid), ("huge", huge)]:
            self.tools.register(KadenceToolSpec(name, name, schema({}), handler))
            result = await self.tools.invoke(name, {})
            self.assertFalse(result["ok"])
            self.assertNotIn("SECRET", json.dumps(result))
        self.assertTrue((await self.tools.invoke("probe", {"value": 1}))["ok"])

    async def test_close_denies_new_work(self):
        await self.tools.close()
        self.assertEqual((await self.tools.invoke("probe", {"value": 1}))["error"]["code"], "unavailable")


class CompanionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ContextStore(Path(self.temp.name))
        await self.store.start()
        self.tools = make_local_tools(self.store)
        self.c = Companion(self.tools, self.store)

    async def asyncTearDown(self):
        await self.tools.close()
        self.temp.cleanup()

    async def test_voice_confirmation_commit_restart_recall_and_forget(self):
        thinker = Thinker({"tool":"remember","arguments":{"text":"The spare key is in the blue drawer"}})
        text = "Please keep the detail we just discussed"
        reply = await self.c.respond(text, thinker)
        self.assertIn("confirm", reply)
        self.assertEqual((await self.store.perform("list"))["items"], [])
        # Only actual completed speech makes the next 'yes' authoritative.
        self.c.commit_spoken(text, reply)
        saved = await self.c.respond("Yes", thinker)
        self.assertIn("Saved as note", saved)
        self.c.commit_spoken("Yes", saved)
        other = ContextStore(Path(self.temp.name))
        await other.start()
        rows = (await other.perform("list", query="blue"))["items"]
        self.assertEqual(len(rows), 1)
        planner = Thinker({"tool": "forget", "arguments": {"id": rows[0]["id"]}})
        reply = await self.c.respond("Delete that note", planner)
        self.assertIn("blue drawer", reply)
        self.c.commit_spoken("Delete that note", reply)
        self.assertIn("deleted", await self.c.respond("Yes please", thinker))
        self.assertEqual((await other.perform("list"))["items"], [])

    async def test_unheard_cancelled_or_expired_confirmation_never_writes(self):
        thinker = Thinker({"tool":"remember","arguments":{"text":"test fact"}})
        reply = await self.c.respond("Keep this detail", thinker)
        await self.c.respond("yes", thinker)
        self.assertEqual((await self.store.perform("list"))["items"], [])
        reply = await self.c.respond("Keep this detail", thinker)
        self.c.commit_spoken("remember", reply)
        self.c.abort_turn()
        await self.c.respond("yes", thinker)
        self.assertEqual((await self.store.perform("list"))["items"], [])
        reply = await self.c.respond("Keep this detail", thinker)
        self.c.commit_spoken("remember", reply)
        with patch("kcore.companion.time.monotonic", return_value=time.monotonic()+100):
            await self.c.respond("yes", thinker)
        self.assertEqual((await self.store.perform("list"))["items"], [])

    async def test_model_cannot_smuggle_write_authority_or_hardware(self):
        for proposal in [{"tool": "body.pose", "arguments": {"yaw": 1}},
                         {"tool": "remember", "arguments": {"text": "hidden"}, "confirmed": True}]:
            await self.c.respond("hello", Thinker(proposal))
        self.assertEqual((await self.store.perform("list"))["items"], [])

    async def test_tool_state_recovery_and_bounded_history(self):
        states=[]
        async def sink(state): states.append(state)
        reply = await self.c.respond("What is 7 times 8?", Thinker({"tool": "calculate", "arguments": {"expression": "7*8"}}), state_sink=sink)
        self.assertEqual(states, ["tool-working", "thinking"])
        self.assertIn("56", reply)
        self.assertEqual(len(self.c.history), 0)
        for _ in range(20): self.c.commit_spoken("a" * 1000, "b" * 1000)
        self.assertLessEqual(len(self.c.history), 8)
        self.assertLessEqual(sum(len(a)+len(b) for a,b in self.c.history), 12000)

    async def test_plain_turn_receives_only_completed_context(self):
        self.c.commit_spoken("Who wrote Dune?", "Frank Herbert.")
        thinker = Thinker({"reply": "He was American."})
        self.assertEqual(await self.c.respond("What nationality was he?", thinker), "He was American.")
        self.assertIn("Frank Herbert", thinker.prompts[0])
        self.assertEqual(len(self.c.history), 1)

    async def test_offline_reasoner_local_reads_and_task_lifecycle(self):
        offline = Thinker(RuntimeError("provider down"))
        self.assertIn("It's", await self.c.respond("What time is it?", offline))
        reply=await self.c.respond("Add check the tyres to my list", offline)
        self.c.commit_spoken("add",reply)
        self.assertIn("Added",reply)
        self.assertIn("tyres",await self.c.respond("Read my list",offline))
        row=(await self.store.perform("list",kind="task"))["items"][0]
        reply=await self.c.respond("finish that",Thinker({"tool":"task_done","arguments":{"id":row["id"]}}))
        self.c.commit_spoken("finish",reply)
        self.assertIn("done",await self.c.respond("yes",offline))
        self.assertEqual((await self.store.perform("list",kind="task"))["items"],[])

    async def test_explicit_local_save_needs_no_redundant_confirmation(self):
        offline=Thinker(RuntimeError("provider down"))
        reply=await self.c.respond("Remember that the spare cable is in the drawer",offline)
        self.assertIn("Saved as note",reply)
        self.assertEqual(len((await self.store.perform("list"))["items"]),1)
        self.assertEqual(offline.prompts,[])

    async def test_literal_search_and_failed_calculation(self):
        await self.store.perform("add",text="100% reliable",kind="memory")
        self.assertEqual(len((await self.store.perform("list",query="%"))["items"]),1)
        self.assertEqual((await self.store.perform("list",query="' OR 1=1 --"))["items"],[])
        for expression in ["__import__('os').system('id')", "2**100000000", "1/0", "1e999", "(-1)**0.5", "True+1"]:
            with self.subTest(expression=expression), self.assertRaises((ValueError,ZeroDivisionError)):
                calculate(expression)
        self.assertEqual(calculate("(20-4)*3/2"),24)


class WireTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_authentication_and_legacy_diagnostic(self):
        token="a"*32
        def stream(magic, auth=b""):
            reader=asyncio.StreamReader()
            reader.feed_data(struct.pack("!4sHH",magic,16000,60)+auth+b"\x00\x03abc\x00\x00")
            reader.feed_eof()
            return reader
        self.assertEqual((await read_wire_turn(stream(b"KDV2",token.encode()),expected_token=token)).packets,(b"abc",))
        self.assertEqual((await read_wire_turn(stream(b"KDV1"))).packets,(b"abc",))
        for reader in [stream(b"KDV1"),stream(b"KDV2",b"b"*32)]:
            with self.assertRaises(ValueError): await read_wire_turn(reader,expected_token=token)


if __name__ == "__main__":
    unittest.main()
