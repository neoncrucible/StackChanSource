"""Bounded read-only adapters. Configuration owns destinations, never the model.

API contracts: https://open-meteo.com/en/docs and
https://developers.home-assistant.io/docs/api/rest/
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import urlsplit

from .local_tools import schema, string
from .tool_bridge import KadenceToolBoundary, KadenceToolSpec

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"


async def read_json(client, url: str, *, params=None, headers=None) -> dict:
    async with client.stream("GET", url, params=params, headers=headers) as response:
        response.raise_for_status()
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > 65536:
                raise ValueError("integration response exceeds limit")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("integration returned an invalid object")
    return result


def register_integrations(tools: KadenceToolBoundary, env=None) -> None:
    values = os.environ if env is None else env

    async def weather(args):
        import httpx
        async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
            places = await read_json(client, GEOCODE, params={"name": args["location"], "count": 10, "language": "en", "format": "json"})
            candidates = places.get("results", [])
            country = args.get("country", "").casefold()
            region = args.get("region", "").casefold()
            candidates = [p for p in candidates if (not country or p.get("country_code", "").casefold() == country)
                          and (not region or any(region in str(p.get(k, "")).casefold() for k in ("admin1", "admin2", "admin3")))]
            exact = [p for p in candidates if p.get("name", "").casefold() == args["location"].casefold()]
            if exact:
                candidates = exact
            if len(candidates) != 1:
                return {"needs_location": True, "candidates": [", ".join(str(p.get(k, "")) for k in ("name", "admin1", "country_code"))[:120] for p in candidates[:3]]}
            place = candidates[0]
            offset = args.get("day", 0)
            data = await read_json(client, FORECAST, params={
                "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": offset + 1,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            })
            daily = data["daily"]
            return {"location": place["name"], "date": daily["time"][offset],
                    "high_c": daily["temperature_2m_max"][offset], "low_c": daily["temperature_2m_min"][offset],
                    "rain_percent": daily["precipitation_probability_max"][offset],
                    "weather_code": daily["weather_code"][offset], "source": "Open-Meteo"}

    tools.register(KadenceToolSpec("weather", "Daily forecast for a named town. Disambiguate with two-letter country and region; day 0=today, 1=tomorrow, up to 6. Ask for a place if unknown.",
        schema({"location": string(80), "country": {"type": "string", "pattern": "^[A-Za-z]{2}$"}, "region": string(80),
                "day": {"type": "integer", "minimum": 0, "maximum": 6}}, "location"), weather, timeout=9))

    base = values.get("KADENCE_HA_URL", "").rstrip("/")
    token = values.get("KADENCE_HA_TOKEN", "")
    entities = tuple(v.strip() for v in values.get("KADENCE_HA_ENTITIES", "").split(",") if v.strip())
    if not any((base, token, entities)):
        return
    parsed = urlsplit(base)
    if (not all((base, token, entities)) or parsed.scheme not in ("https", "http") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")
            or len(entities) > 8 or any(not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", item) for item in entities)):
        raise ValueError("optional home integration configuration is incomplete or invalid")

    async def home_status(args):
        import httpx
        async with httpx.AsyncClient(timeout=4, follow_redirects=False, trust_env=False) as client:
            async def read(entity):
                payload = await read_json(client, base + "/api/states/" + entity, headers={"Authorization": "Bearer " + token})
                if payload.get("entity_id") != entity:
                    raise ValueError("unexpected home entity")
                return {"name": str(payload.get("attributes", {}).get("friendly_name", entity))[:80],
                        "state": str(payload["state"])[:80]}
            return {"items": await asyncio.gather(*(read(entity) for entity in entities))}
    tools.register(KadenceToolSpec("home_status", "Read status of only the home entities configured by the owner. Cannot control devices.", schema({}), home_status, timeout=5))
