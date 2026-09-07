from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from kcore.integrations import register_integrations
from kcore.local_tools import make_local_tools


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = make_local_tools(None)
        self.original_client = httpx.AsyncClient

    async def asyncTearDown(self): await self.tools.close()

    def client(self, handler):
        return patch("httpx.AsyncClient", side_effect=lambda **kwargs: self.original_client(transport=httpx.MockTransport(handler), **kwargs))

    async def test_weather_fixed_destinations_and_location_disambiguation(self):
        register_integrations(self.tools, {})
        calls=[]
        def handler(request):
            calls.append(request)
            self.assertEqual(request.method,"GET")
            if request.url.host=="geocoding-api.open-meteo.com":
                return httpx.Response(200,json={"results":[
                    {"name":"Newport","country_code":"GB","admin2":"Isle of Wight","latitude":50.7,"longitude":-1.29},
                    {"name":"Newport","country_code":"GB","admin2":"Wales","latitude":51.58,"longitude":-2.99}]})
            self.assertEqual(request.url.host,"api.open-meteo.com")
            self.assertEqual(request.url.params["latitude"],"50.7")
            return httpx.Response(200,json={"daily":{"time":["2026-09-07"],"temperature_2m_max":[20],"temperature_2m_min":[12],"precipitation_probability_max":[10],"weather_code":[1]}})
        with self.client(handler):
            ambiguous=await self.tools.invoke("weather",{"location":"Newport","country":"GB"})
            self.assertTrue(ambiguous["data"]["needs_location"])
            self.assertEqual(len(calls),1)
            result=await self.tools.invoke("weather",{"location":"Newport","country":"GB","region":"Isle of Wight"})
            self.assertEqual(result["data"]["high_c"],20)

    async def test_home_reads_only_configured_entities_and_never_follows_redirects(self):
        register_integrations(self.tools,{"KADENCE_HA_URL":"http://home.local:8123","KADENCE_HA_TOKEN":"private-test-token","KADENCE_HA_ENTITIES":"light.desk,sensor.room"})
        visited=[]
        def handler(request):
            self.assertEqual(request.method,"GET")
            self.assertEqual(request.headers["Authorization"],"Bearer private-test-token")
            visited.append(request.url.path)
            entity=request.url.path.rsplit("/",1)[1]
            return httpx.Response(200,json={"entity_id":entity,"state":"on","attributes":{"friendly_name":entity,"secret_attribute":"excluded"}})
        with self.client(handler): result=await self.tools.invoke("home_status",{})
        self.assertEqual(set(visited),{"/api/states/light.desk","/api/states/sensor.room"})
        self.assertNotIn("secret_attribute",str(result))
        self.assertFalse((await self.tools.invoke("home_status",{"entity":"lock.front"}))["ok"])
        def redirect(request): return httpx.Response(302,headers={"Location":"http://untrusted.example"})
        with self.client(redirect): result=await self.tools.invoke("home_status",{})
        self.assertFalse(result["ok"])
        self.assertNotIn("private-test-token",str(result))

    async def test_optional_home_configuration_fails_closed(self):
        register_integrations(self.tools,{})
        self.assertFalse(self.tools.has_tool("home_status"))
        other=make_local_tools(None)
        try:
            with self.assertRaises(ValueError):
                register_integrations(other,{"KADENCE_HA_URL":"http://user:password@host","KADENCE_HA_TOKEN":"private","KADENCE_HA_ENTITIES":"sensor.room"})
            self.assertFalse(other.has_tool("home_status"))
        finally: await other.close()

    async def test_external_failure_and_oversized_body_do_not_block_local_tools(self):
        register_integrations(self.tools,{})
        def oversized(request): return httpx.Response(200,content=b"x"*70000)
        with self.client(oversized): result=await self.tools.invoke("weather",{"location":"London"})
        self.assertFalse(result["ok"])
        self.assertTrue((await self.tools.invoke("clock",{}))["ok"])


if __name__=="__main__": unittest.main()
