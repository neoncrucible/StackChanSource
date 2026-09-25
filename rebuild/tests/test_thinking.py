import asyncio
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from kcore.companion import Companion
from kcore.desktop_worker import DesktopController
from kcore.thinking import PLAN_FORMAT, ThinkingServiceError, request_plan
from kcore.tool_bridge import KadenceToolBoundary
from kcore.voice_providers import OllamaThinker


def response(content, *, done=True, **extra):
    return httpx.Response(200, content=json.dumps({"message": {"content": content}, "done": done, **extra}) + "\n")


def client(handler):
    real = httpx.AsyncClient
    return patch("httpx.AsyncClient", side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


class OllamaPlanning(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_success_is_not_reply_success_and_plan_uses_schema(self):
        from kcore.ollama_models import installed_models
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen3.5:4b"}]})
            payload = json.loads(request.content)
            # The pre-fix request elicited plain prose, which the JSON planner
            # misreported as an unreachable service. Constrain that boundary.
            if payload.get("format") == PLAN_FORMAT:
                return response('{"reply":"Ready, Boss."}')
            return response("Ready, Boss.")

        events = []
        companion = Companion(KadenceToolBoundary(), emit=lambda *args: events.append(args))
        with client(handler):
            self.assertEqual(await installed_models(), ["qwen3.5:4b"])
            self.assertEqual(await companion.respond("Hello", OllamaThinker(model="qwen3.5:4b")), "Ready, Boss.")
        self.assertEqual(events, [])
        payload = json.loads(requests[-1].content)
        self.assertFalse(payload["think"])
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["options"]["num_predict"], 1024)
        self.assertTrue(all(request.url.host == "127.0.0.1" for request in requests))

    async def test_valid_tool_plan_still_requires_spoken_confirmation(self):
        from kcore.context_store import ContextStore
        from kcore.local_tools import make_local_tools
        with tempfile.TemporaryDirectory() as root:
            from pathlib import Path
            store = ContextStore(Path(root)); await store.start()
            tools = make_local_tools(store)
            companion = Companion(tools, store)
            with client(lambda _: response('{"tool":"remember","arguments":{"text":"fixture fact"}}')):
                reply = await companion.respond("Please keep the detail we discussed", OllamaThinker(model="mine"))
            self.assertIn("confirm", reply)
            self.assertEqual((await store.perform("list"))["items"], [])
            companion.commit_spoken("Please keep the detail we discussed", reply)
            self.assertIn("Saved as note", await companion.respond("Yes", OllamaThinker(model="mine")))
            await tools.close()

    async def test_model_errors_are_distinct_and_never_export_raw_bodies(self):
        cases = [
            (httpx.Response(404, json={"error": "PRIVATE missing model"}), "model_missing", 404),
            (httpx.Response(400, json={"error": "PRIVATE unsupported option"}), "http_error", 400),
            (httpx.Response(500, json={"error": "PRIVATE load failed"}), "model_error", 500),
            (httpx.Response(200, content='{"error":"PRIVATE runner failed"}\n'), "model_error", None),
            (httpx.Response(200, content="PRIVATE bad NDJSON\n"), "invalid_response", None),
            (response(""), "empty_response", None),
            (response('{"reply":"PRIVATE"}', done_reason="length"), "truncated_response", None),
            (response('{"reply":"PRIVATE"}', done=False), "truncated_response", None),
            (response("PRIVATE" * 2000), "response_limit", None),
            (response("PRIVATE plain prose"), "invalid_plan", None),
        ]
        for reply, reason, status in cases:
            with self.subTest(reason=reason, status=status):
                events = []
                companion = Companion(KadenceToolBoundary(), emit=lambda *args: events.append(args))
                with client(lambda _: reply):
                    spoken = await companion.respond("PRIVATE user text", OllamaThinker(model="mine"))
                data = events[-1][1]
                self.assertEqual(events[-1][0], "runtime_issue")
                self.assertEqual(data["reason"], reason)
                self.assertEqual(data["provider"], "ollama")
                self.assertEqual(data["provider_stage"], "reasoning")
                self.assertEqual(data.get("http_status"), status)
                self.assertNotIn("PRIVATE", json.dumps(events) + spoken)
                self.assertNotIn("trouble reaching", spoken)

    async def test_connection_and_read_timeouts_keep_their_reason(self):
        for error, reason in [(httpx.ConnectError("PRIVATE"), "unavailable"),
                              (httpx.ReadTimeout("PRIVATE"), "timeout")]:
            def fail(_): raise error
            with self.subTest(reason=reason), client(fail):
                with self.assertRaises(ThinkingServiceError) as caught:
                    await request_plan(OllamaThinker(model="mine"), "hello")
            self.assertEqual(caught.exception.reason, reason)

    async def test_partial_plan_timeout_and_cancellation_do_not_execute(self):
        closed = asyncio.Event()

        class Slow:
            async def stream_reply(self, prompt):
                try:
                    yield '{"tool":"remember","arguments":{"text":"partial"}}'
                    await asyncio.Event().wait()
                finally:
                    closed.set()

        with patch("kcore.thinking.PLAN_TIMEOUT", .02):
            with self.assertRaises(ThinkingServiceError) as caught:
                await request_plan(Slow(), "hello")
        self.assertEqual(caught.exception.reason, "timeout")
        self.assertTrue(closed.is_set())
        closed.clear()
        companion = Companion(KadenceToolBoundary())
        task = asyncio.create_task(companion.respond("hello", Slow()))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(closed.is_set())
        self.assertIsNone(companion._proposed)

    async def test_invalid_or_ambiguous_plans_never_reach_tools(self):
        for raw in ['{"reply":"first","reply":"second"}', '{"tool":"clock","arguments":null}',
                    '{"tool":[],"arguments":{}}', '{"reply":"ok","confirmed":true}',
                    '{"tool":"clock","arguments":{"number":NaN}}', '[]']:
            class Plain:
                async def stream_reply(self, prompt): yield raw
            with self.subTest(raw=raw), self.assertRaises(ThinkingServiceError) as caught:
                await request_plan(Plain(), "hello")
            self.assertEqual(caught.exception.reason, "invalid_plan")


class ReplyCheck(unittest.IsolatedAsyncioTestCase):
    async def test_reply_check_uses_voice_context_without_executing_tools(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            controller = DesktopController(lambda *args: events.append(args), directory=root)
            await controller.start()
            try:
                seen = []
                def handler(request):
                    seen.append(json.loads(request.content))
                    return response('{"reply":"PRIVATE generated text"}')
                with client(handler), patch.object(controller.services.tools, "invoke", new_callable=AsyncMock) as invoke:
                    result = await controller.command("ollama_reply_check", {"model": "qwen3.5:4b"})
                    self.assertTrue(result["passed"])
                    invoke.assert_not_awaited()
                prompt = seen[0]["messages"][-1]["content"]
                self.assertIn("REGISTERED TOOLS:", prompt)
                self.assertIn("COMPLETED EXCHANGES:\n[]", prompt)
                self.assertEqual(seen[0]["format"], PLAN_FORMAT)
                self.assertNotIn("PRIVATE", json.dumps(events) + json.dumps(result))
                with client(lambda _: response('{"tool":"remember","arguments":{"text":"PRIVATE"}}')):
                    result = await controller.command("ollama_reply_check", {"model": "mine"})
                self.assertFalse(result["passed"])
                self.assertEqual(result["reason"], "invalid_plan")
                self.assertEqual((await controller.services.context.perform("list"))["items"], [])
                controller.state = "running"
                with client(lambda _: self.fail("A running server must not start a probe")):
                    with self.assertRaisesRegex(ValueError, "Stop the server"):
                        await controller.command("ollama_reply_check", {"model": "mine"})
            finally:
                await controller.close()

    async def test_check_failure_reports_local_problem_not_discovery_success(self):
        with tempfile.TemporaryDirectory() as root:
            events = []
            controller = DesktopController(lambda *args: events.append(args), directory=root)
            await controller.start()
            try:
                with client(lambda _: httpx.Response(500, json={"error": "PRIVATE"})):
                    result = await controller.command("ollama_reply_check", {"model": "mine"})
                self.assertFalse(result["passed"])
                self.assertEqual(result["reason"], "model_error")
                self.assertEqual(events[-1][1]["http_status"], 500)
                self.assertNotIn("PRIVATE", json.dumps(events) + json.dumps(result))
            finally:
                await controller.close()
