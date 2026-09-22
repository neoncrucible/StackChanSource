import json
import unittest
from unittest.mock import patch

import httpx

from kcore.ollama_models import DEFAULT_OLLAMA_MODEL, installed_models, model_name
from kcore.desktop_worker import settings_from_control


class Models(unittest.IsolatedAsyncioTestCase):
    async def query(self, handler):
        real = httpx.AsyncClient
        with patch('httpx.AsyncClient', side_effect=lambda **kw: real(transport=httpx.MockTransport(handler), **kw)):
            return await installed_models()

    async def test_discovery_keeps_exact_tags_and_uses_local_endpoint(self):
        def handler(request):
            self.assertEqual(str(request.url), 'http://127.0.0.1:11434/api/tags')
            self.assertEqual(request.method, 'GET')
            return httpx.Response(200, json={'models':[{'name':'mine:latest'}, {'name':DEFAULT_OLLAMA_MODEL}, {'name':'mine:latest'}]})
        self.assertEqual(await self.query(handler), ['mine:latest', DEFAULT_OLLAMA_MODEL])
        self.assertEqual(await self.query(lambda _: httpx.Response(200,json={'models':[]})), [])

    async def test_unavailable_malformed_and_oversized_are_contained(self):
        for response in (httpx.Response(503), httpx.Response(200,json={'models':[{'name':'bad name'}]}),
                         httpx.Response(200,content=b'x'*262145), httpx.Response(200,json=[])):
            with self.subTest(response=response), self.assertRaisesRegex(RuntimeError,'saved selection is unchanged'):
                await self.query(lambda _: response)

    def test_default_and_explicit_tags(self):
        self.assertEqual(model_name(''), DEFAULT_OLLAMA_MODEL)
        self.assertEqual(model_name(' custom/model:q4 '), 'custom/model:q4')
        with self.assertRaises(ValueError): model_name('qwen 3.5')
        args={'port':'COM4','ssid':'fixture','lan_host':'192.168.1.2','thinker_provider':'ollama'}
        self.assertEqual(settings_from_control(args).providers.ollama_model,DEFAULT_OLLAMA_MODEL)
        with self.assertRaises(ValueError): settings_from_control(dict(args,ollama_model='qwen 3.5'))
