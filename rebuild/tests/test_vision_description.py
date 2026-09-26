"""Official Interactions response contract and the complete spoken look path."""
import asyncio
import base64
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from kcore.appliance import ApplianceSettings, KadenceAppliance
from kcore.camera_manager import CameraFrame
from kcore.services import LocalServices
from kcore.vision import DeskVision
from kcore.vision_provider import describe_image, description_text, VisionServiceError
from kcore.voice_providers import VoiceProviderSettings
from kcore.protocol import Envelope, MessageKind
from test_appliance_candidate import Adapters, Device

SCENE = "A red mug sits beside a blue notebook on the desk."
# REST shape from Google's May 2026 migration guide. Include input/thought/tool
# text to prove we only speak actual model_output content.
RESPONSE = {"status":"completed", "steps":[
    {"type":"user_input", "content":[{"type":"text","text":"private input"}]},
    {"type":"thought", "summary":[{"type":"text","text":"private thought"}]},
    {"type":"google_search_result", "result":{"text":"private tool text"}},
    {"type":"model_output", "content":[{"type":"text","text":SCENE}]},
]}


def frame():
    out=io.BytesIO(); Image.new("RGB",(64,48),"red").save(out,format="PNG")
    return CameraFrame("test-request","test-frame","unitv2-camera",out.getvalue(),64,48,time.time(),2,0)


class DescriptionTests(unittest.IsolatedAsyncioTestCase):
    def client(self, handler):
        constructor=httpx.AsyncClient
        return patch("httpx.AsyncClient", side_effect=lambda **kw:constructor(transport=httpx.MockTransport(handler),**kw))

    async def test_current_response_and_stateless_request_contract(self):
        seen=[]
        def handle(request):
            seen.append(request)
            return httpx.Response(200,json=RESPONSE)
        with self.client(handle):
            result=await describe_image(frame().png,"What can you see?",VoiceProviderSettings("fake","secret-test-key"))
        self.assertEqual(result,SCENE)
        body=json.loads(seen[0].content)
        self.assertEqual(seen[0].url.path,"/v1beta/interactions")
        self.assertEqual(seen[0].headers["Api-Revision"],"2026-05-20")
        self.assertIs(body["store"],False)
        self.assertNotIn("previous_interaction_id",body)
        self.assertEqual(base64.b64decode(body["input"][1]["data"]),frame().png)

    def test_only_complete_model_text_is_accepted(self):
        self.assertEqual(description_text({"outputs":[{"type":"text","text":SCENE}]}),SCENE)
        cases=[([],"invalid_response"), ({},"invalid_response"),
            ({"steps":{},"outputs":[{"type":"text","text":SCENE}]},"invalid_response"),
            ({"steps":[],"outputs":[{"type":"text","text":SCENE}]},"empty_response"),
            ({"steps":[{"type":"model_output","content":[{"type":"text","text":None}]}]},"invalid_response"),
            ({"steps":RESPONSE["steps"][:3]},"empty_response"),
            ({**RESPONSE,"status":"in_progress"},"incomplete"),
            ({**RESPONSE,"status":"requires_action"},"incomplete"),
            ({"status":"failed","error":{"code":"SAFETY","message":"private"}},"blocked")]
        for response,reason in cases:
            with self.subTest(reason=reason,response=response):
                with self.assertRaises(VisionServiceError) as raised: description_text(response)
                self.assertEqual(raised.exception.reason,reason)
                self.assertNotIn("private",str(raised.exception))

    async def test_http_failures_are_specific_and_never_leak_provider_bodies(self):
        for status,reason in [(401,"authentication"),(403,"authentication"),(404,"model_missing"),(429,"quota"),(400,"http_error")]:
            with self.subTest(status=status),self.client(lambda r:httpx.Response(status,text="PRIVATE_API_KEY IMAGE TRANSCRIPT")):
                with self.assertRaises(VisionServiceError) as raised:
                    await describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake"))
                self.assertEqual(raised.exception.reason,reason)
                self.assertEqual(raised.exception.http_status,status)
                self.assertNotIn("PRIVATE",str(raised.exception))

    async def test_transient_retry_is_bounded_and_quota_is_not_retried(self):
        statuses=[]
        def transient(request):
            statuses.append(1)
            return httpx.Response(503 if len(statuses)==1 else 200,json=RESPONSE)
        with self.client(transient):
            self.assertEqual(await describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake")),SCENE)
        self.assertEqual(len(statuses),2)
        statuses.clear()
        def quota(request):
            statuses.append(1); return httpx.Response(429)
        with self.client(quota),self.assertRaises(VisionServiceError):
            await describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake"))
        self.assertEqual(len(statuses),1)

    async def test_slow_trickle_has_a_total_deadline_and_can_be_cancelled(self):
        closed=asyncio.Event()
        class Slow(httpx.AsyncByteStream):
            async def __aiter__(self):
                while True:
                    await asyncio.sleep(.01); yield b" "
            async def aclose(self): closed.set()
        with self.client(lambda r:httpx.Response(200,stream=Slow())),patch("kcore.vision_provider.DESCRIPTION_TIMEOUT",.045):
            started=time.monotonic()
            with self.assertRaises(VisionServiceError) as raised:
                await describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake"))
            self.assertEqual(raised.exception.reason,"timeout")
            self.assertLess(time.monotonic()-started,.5)
        self.assertTrue(closed.is_set())
        closed.clear()
        with self.client(lambda r:httpx.Response(200,stream=Slow())):
            task=asyncio.create_task(describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake")))
            await asyncio.sleep(.025);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(closed.is_set())

    async def test_malformed_and_oversize_responses_fail_without_raw_details(self):
        for value,reason in [(b"private malformed", "invalid_response"),(b"x"*(128*1024+1),"response_limit")]:
            with self.subTest(reason=reason),self.client(lambda r:httpx.Response(200,content=value)):
                with self.assertRaises(VisionServiceError) as raised:
                    await describe_image(frame().png,"Look",VoiceProviderSettings(None,"fake"))
                self.assertEqual(raised.exception.reason,reason)


class SpokenLookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.events=[];self.spoken=[]
        self.services=LocalServices(directory=Path(self.temp.name));await self.services.start()
        settings=ApplianceSettings("COM4",115200,4800,.01,"test","test","127.0.0.1",VoiceProviderSettings("fake","fake"))
        self.app=KadenceAppliance(settings,services=self.services,emit=lambda n,d:self.events.append((n,dict(d))))
        await self.app._start_companion();await self.app._start_voice_server()
        self.device=Device(self.app);self.app._body=self.device
        self.app.camera.acquire=AsyncMock(return_value=frame())
        self.adapters=Adapters();self.adapters.text="What can you see?"
        original=self.adapters.synthesize
        async def synthesize(text):
            self.spoken.append(text)
            async for audio in original(text):yield audio
        self.adapters.synthesize=synthesize
        self.providers=patch("kcore.voice_wire.LiveVoiceProviders.from_settings",return_value=self.adapters);self.providers.start()
        constructor=httpx.AsyncClient
        self.http_handler=lambda r:httpx.Response(200,json=RESPONSE)
        self.http=patch("httpx.AsyncClient",side_effect=lambda **kw:constructor(transport=httpx.MockTransport(self.handle),**kw));self.http.start()

    async def handle(self, request):
        result=self.http_handler(request)
        return await result if hasattr(result,"__await__") else result

    async def asyncTearDown(self):
        await self.app.close();await self.services.close()
        self.providers.stop();self.http.stop();self.temp.cleanup()

    async def turn(self):
        self.app._begin_voice_turn(self.device,Envelope(MessageKind.EVENT,"voice.request",{"trigger":"touch"}))
        task=self.app._voice_task
        await asyncio.wait_for(task,2);await asyncio.sleep(0)

    async def test_captured_frame_reaches_api_description_speech_and_completed_history(self):
        await self.turn()
        self.assertEqual(self.spoken,[SCENE])
        self.assertEqual(list(self.app._companion.history),[("What can you see?",SCENE)])
        self.assertEqual(self.app.vision.description,SCENE)
        self.assertEqual(self.app.vision.source_device,"unitv2-camera")
        self.app.camera.acquire.assert_awaited_once()
        metadata=[data for name,data in self.events if name=="vision_description"]
        self.assertEqual(metadata[-1]["state"],"complete")
        self.assertEqual(metadata[-1]["chars"],len(SCENE))
        self.assertNotIn(SCENE,json.dumps(metadata))
        self.assertGreater(self.device.played,0)

    async def test_failed_description_is_spoken_precisely_and_next_turn_recovers(self):
        self.http_handler=lambda r:httpx.Response(429,text="PRIVATE_RESPONSE_BODY")
        await self.turn()
        self.assertIn("quota",self.spoken[-1])
        self.assertEqual(self.app.vision.description_state,"failed")
        self.assertEqual(self.app.vision.description,"")
        failures=[d for n,d in self.events if n=="vision_description" and d["state"]=="failed"]
        self.assertEqual(failures[-1]["http_status"],429)
        self.assertNotIn("PRIVATE_RESPONSE_BODY",json.dumps(self.events))
        self.http_handler=lambda r:httpx.Response(200,json=RESPONSE)
        await self.turn()
        self.assertEqual(self.spoken[-1],SCENE)

    async def test_touch_cancel_during_description_leaves_no_stale_speech_and_next_look_works(self):
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def hung(request):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        self.http_handler=hung
        self.app._begin_voice_turn(self.device,Envelope(MessageKind.EVENT,"voice.request",{"trigger":"touch"}))
        await asyncio.wait_for(entered.wait(),1)
        await self.app._handle_touch_cancel(self.device,Envelope(MessageKind.EVENT,"voice.touch-cancel",{"trigger":"touch"}))
        await asyncio.wait_for(cancelled.wait(),1)
        self.assertFalse(self.spoken);self.assertFalse(self.app._companion.history)
        self.assertFalse(self.app._connections);self.assertIsNone(self.app._turn_token)
        self.http_handler=lambda r:httpx.Response(200,json=RESPONSE)
        await self.turn();self.assertEqual(self.spoken,[SCENE])

    async def test_privacy_or_replaced_frame_cannot_publish_an_old_description(self):
        entered=asyncio.Event();resume=asyncio.Event()
        async def delayed(request):
            entered.set();await resume.wait();return httpx.Response(200,json=RESPONSE)
        self.http_handler=delayed
        task=asyncio.create_task(self.app.look_camera("Look"))
        await asyncio.wait_for(entered.wait(),1)
        self.app.camera.config=replace(self.app.camera.config,privacy=True)
        self.app.vision.clear();resume.set()
        with self.assertRaises((RuntimeError,asyncio.CancelledError)):await task
        self.assertIsNone(self.app.vision.png);self.assertEqual(self.app.vision.description,"")
        self.assertFalse(any(n=="vision_description" and d["state"]=="complete" for n,d in self.events))


if __name__=="__main__":unittest.main()
