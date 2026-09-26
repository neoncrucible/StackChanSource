"""Overlap, validation, warm-up and privacy properties of the fast voice path."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from kcore.companion import Companion
from kcore.identity import KADENCE_IDENTITY
from kcore.thinking import request_plan
from kcore.tool_bridge import KadenceToolBoundary
from kcore.voice_providers import OllamaThinker, VoiceProviderSettings
from kcore.voice_wire import process_wire_turn, VoiceWireTurn


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, invalid=False, cancel=False):
        prepared = asyncio.Event(); model_finished = asyncio.Event(); played = []; renders = []
        private = "The first sentence is ready."
        class Providers:
            timings = {}
            async def transcribe_file(self, *args, **kwargs): return "Tell me something."
            async def stream_reply(self, prompt):
                yield '{"reply":"' + private + ' '
                await asyncio.wait_for(prepared.wait(), 2)
                # Native rendering is active but the reply is not accepted yet.
                self.assert_unheard()
                if cancel: await asyncio.Event().wait()
                yield 'Here is the remainder."' + (',"tool":"remember","arguments":{}}' if invalid else '}')
                model_finished.set()
            def assert_unheard(self):
                if played: raise AssertionError("Unvalidated speech escaped")
            async def synthesize_pcm(self, text, *, pcm_sink=None, **kwargs):
                renders.append(text)
                pcm = (b"\1\0" if text == private else b"\2\0") * 160
                if pcm_sink: await pcm_sink(pcm)
                if text == private: prepared.set()
                return pcm
        providers = Providers()
        providers.stt = providers.thinker = providers.tts = providers
        companion = Companion(KadenceToolBoundary())
        async def sink(pcm):
            self.assertTrue(model_finished.is_set())
            played.append(pcm)
        with patch("kcore.voice_wire.LiveVoiceProviders.from_settings", return_value=providers):
            task = asyncio.create_task(process_wire_turn(VoiceWireTurn(16000, 60, (b"abc",)),
                settings=VoiceProviderSettings("fixture", "fixture"), companion=companion, pcm_sink=sink))
            if cancel:
                await asyncio.wait_for(prepared.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
                self.assertEqual(played, [])
            else:
                result = await asyncio.wait_for(task, 3)
                self.assertEqual(result.pcm, b"".join(played))
                if invalid:
                    self.assertNotIn(private, result.reply)
                    self.assertTrue(all(chunk == b"\2\0" * 160 for chunk in played))
                else:
                    self.assertEqual(renders, [private, "Here is the remainder."])
                    self.assertEqual(played, [b"\1\0" * 160, b"\2\0" * 160])
            self.assertFalse(companion.history)  # Device proof has not arrived.
        self.assertFalse([task for task in asyncio.all_tasks() if task.get_name() == "kadence-speech-draft"])

    async def test_render_overlaps_reasoning_but_audio_waits_for_validation(self):
        await self.exercise()

    async def test_invalid_mixed_plan_discards_private_audio(self):
        await self.exercise(invalid=True)

    async def test_cancel_during_planning_discards_draft_without_playing(self):
        await self.exercise(cancel=True)

    async def test_partial_tool_has_no_speech_preview(self):
        offered = []
        class Thinker:
            async def stream_reply(self, prompt):
                yield '{"tool":"remember","arguments":{"text":"A sentence. Another."}}'
        async def preview(text): offered.append(text)
        plan = await request_plan(Thinker(), "fixture", preview_sink=preview)
        self.assertEqual(plan["tool"], "remember")
        self.assertEqual(offered, [])

    async def test_ollama_warmup_no_generation_and_metrics_are_numeric_only(self):
        sent = []
        def handler(request):
            payload = json.loads(request.content); sent.append(payload)
            if request.url.path == "/api/generate":
                return httpx.Response(200, json={"done": True})
            return httpx.Response(200, content=json.dumps({"message": {"content": '{"reply":"Ready, Boss."}'},
                "done": True, "load_duration": 2000000, "prompt_eval_duration": 3000000,
                "eval_duration": 4000000, "private": "DO NOT EXPORT"}) + "\n")
        real = httpx.AsyncClient
        thinker = OllamaThinker(model="qwen3.5:2b")
        companion = Companion(KadenceToolBoundary())
        with patch("httpx.AsyncClient", side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            await thinker.warm_up()
            await request_plan(thinker, companion.planner_prompt("Hello"))
        self.assertEqual(sent[0], {"model": "qwen3.5:2b", "stream": False, "keep_alive": "30m"})
        self.assertFalse(sent[1]["think"])
        self.assertEqual(sent[1]["keep_alive"], "30m")
        self.assertEqual(sum(message["content"].count(KADENCE_IDENTITY.system_context()) for message in sent[1]["messages"]), 1)
        self.assertEqual(thinker.timings["ollama_load"], 2)
        self.assertEqual(thinker.timings["ollama_prompt"], 3)
        self.assertEqual(thinker.timings["ollama_generate"], 4)
        self.assertTrue(all(type(value) is int for value in thinker.timings.values()))
        prompt = sent[1]["messages"][1]["content"]
        self.assertLess(prompt.index("REGISTERED TOOLS"), prompt.index("CURRENT LOCAL CLOCK"))


if __name__ == "__main__": unittest.main()
