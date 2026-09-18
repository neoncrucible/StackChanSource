import unittest
from unittest.mock import patch
from kcore.voice_providers import VoiceProviderSettings, LiveVoiceProviders, OllamaThinker, VoiceProviderUnavailable
from kcore.sensors import GestureStatus
from kcore.identity import KADENCE_IDENTITY

class ProviderSelection(unittest.TestCase):
    def test_explicit_local_no_gemini_credentials(self):
        settings=VoiceProviderSettings("stt", None, thinker_provider="ollama", ollama_model="my-kadence:latest")
        self.assertEqual(settings.missing_credentials(), ())
        self.assertIsInstance(LiveVoiceProviders.from_settings(settings).thinker, OllamaThinker)
        self.assertEqual(LiveVoiceProviders.from_settings(settings).thinker.model,"my-kadence:latest")
        with self.assertRaises(ValueError): VoiceProviderSettings(None,None,thinker_provider="other")
        with self.assertRaises(ValueError): VoiceProviderSettings(None,None,thinker_provider="ollama")
        self.assertEqual(VoiceProviderSettings(None,None,thinker_provider="ollama",ollama_model="local").missing_credentials(),("OPENAI_API_KEY",))

    def test_gesture_invalid_and_stale(self):
        p=dict(ok=True,schema=1,state="ready",channel=0,address=0x73,seq=1,age_ms=10,event_seq=1,event_age_ms=10,flags=257)
        status=GestureStatus.from_payload(p)
        self.assertEqual(status.gestures,("right","wave")); self.assertTrue(status.fresh)
        self.assertFalse(GestureStatus.from_payload(dict(p,age_ms=4000)).fresh)
        for key,value in (("flags",512),("seq",True),("address",0x29),("schema",True)):
            with self.subTest(key=key),self.assertRaises(ValueError): GestureStatus.from_payload(dict(p,**{key:value}))

class OllamaStream(unittest.IsolatedAsyncioTestCase):
    async def test_local_request_content_only_and_no_fallback(self):
        import httpx
        observed=[]
        def handler(request):
            observed.append(request)
            return httpx.Response(200,content=b'{"message":{"thinking":"private","content":"hello"},"done":false}\n{"message":{"content":" Boss"},"done":true}\n')
        real=httpx.AsyncClient
        with patch("httpx.AsyncClient",side_effect=lambda **kw:real(transport=httpx.MockTransport(handler),**kw)):
            self.assertEqual([x async for x in OllamaThinker(model="mine").stream_reply("hi")],["hello"," Boss"])
        import json
        payload=json.loads(observed[0].content)
        self.assertEqual(str(observed[0].url),OllamaThinker.endpoint)
        self.assertEqual(payload["model"],"mine")
        self.assertEqual(payload["messages"][0]["content"],KADENCE_IDENTITY.system_context())
        def fail(request): return httpx.Response(404,json={"error":"not installed"})
        with patch("httpx.AsyncClient",side_effect=lambda **kw:real(transport=httpx.MockTransport(fail),**kw)):
            with self.assertRaises(httpx.HTTPStatusError):
                _=[x async for x in OllamaThinker(model="missing").stream_reply("hi")]
