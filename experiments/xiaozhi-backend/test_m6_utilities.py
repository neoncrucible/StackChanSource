from __future__ import annotations

from datetime import datetime, timezone

from kadence_utilities import (
    KadenceReadOnlyUtilities,
    KadenceUtilityError,
    OPENAI_RESPONSES,
    OPEN_METEO_FORECAST,
    OPEN_METEO_GEOCODE,
)


def expect(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS  {label}")


class FakeNetwork:
    def __init__(self):
        self.calls = []

    def __call__(
        self,
        method,
        url,
        *,
        params=None,
        payload=None,
        headers=None,
        timeout=8,
        max_bytes=512_000,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
                "max_bytes": max_bytes,
            }
        )

        if url == OPEN_METEO_GEOCODE:
            name = (params or {}).get("name")
            if name == "Nowhere Invalid":
                return {"results": []}
            return {
                "results": [
                    {
                        "name": "Tokyo" if name == "Tokyo" else "London",
                        "admin1": "Tokyo" if name == "Tokyo" else "England",
                        "country": "Japan" if name == "Tokyo" else "United Kingdom",
                        "latitude": 35.6762 if name == "Tokyo" else 51.5074,
                        "longitude": 139.6503 if name == "Tokyo" else -0.1278,
                        "timezone": "Asia/Tokyo" if name == "Tokyo" else "Europe/London",
                    }
                ]
            }

        if url == OPEN_METEO_FORECAST:
            if (params or {}).get("daily"):
                return {
                    "timezone": "Europe/London",
                    "timezone_abbreviation": "BST",
                    "utc_offset_seconds": 3600,
                    "current": {
                        "temperature_2m": 19.4,
                        "apparent_temperature": 18.7,
                        "weather_code": 61,
                        "precipitation": 0.4,
                        "wind_speed_10m": 8.2,
                    },
                    "daily": {
                        "time": [
                            "2026-08-22",
                            "2026-08-23",
                            "2026-08-24",
                            "2026-08-25",
                            "2026-08-26",
                            "2026-08-27",
                            "2026-08-28",
                        ],
                        "weather_code": [61, 2, 0, 73, 3, 80, 95],
                        "temperature_2m_max": [21, 22, 23, 4, 18, 20, 19],
                        "temperature_2m_min": [14, 13, 12, -1, 11, 12, 13],
                        "precipitation_probability_max": [70, 20, 5, 60, 10, 80, 75],
                    },
                }
            return {
                "timezone": "Asia/Tokyo",
                "timezone_abbreviation": "JST",
                "utc_offset_seconds": 32400,
                "current": {"temperature_2m": 27.0},
            }

        if url == OPENAI_RESPONSES:
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {"title": "Example A", "url": "https://example.test/a"},
                                {"title": "Example A duplicate", "url": "https://example.test/a"},
                            ]
                        },
                    },
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Current factual answer.",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.test/b",
                                        "title": "Example B",
                                    }
                                ],
                            }
                        ],
                    },
                ]
            }

        raise AssertionError(f"unexpected endpoint: {url}")


def main():
    fake = FakeNetwork()
    utilities = KadenceReadOnlyUtilities(
        openai_api_key="test-key",
        openai_model="gpt-5.6-luna",
        request_json=fake,
        now_utc=lambda: datetime(2026, 8, 22, 15, 30, tzinfo=timezone.utc),
    )

    remote_time = utilities.current_datetime({"location": "Tokyo"})
    expect(remote_time["time"] == "00:30", "remote time applies provider UTC offset")
    expect(remote_time["weekday"] == "Sunday", "remote date crosses midnight correctly")
    expect(remote_time["timezone"] == "Asia/Tokyo", "remote timezone is retained")

    weather_today = utilities.weather({"location": "London", "day_offset": 0})
    expect(weather_today["condition"] == "light rain", "daily weather code is described")
    expect(weather_today["current"]["temperature_c"] == 19.4, "current temperature is preserved")
    expect(weather_today["_kadence_ui"]["weather_icon"] == "rain", "rain maps to bounded UI enum")

    weather_tomorrow = utilities.weather({"location": "London", "day_offset": 1})
    expect(weather_tomorrow["condition"] == "partly cloudy", "tomorrow forecast selects requested day")
    expect(weather_tomorrow["_kadence_ui"]["weather_icon"] == "cloud", "cloud maps to bounded UI enum")

    expect(utilities.weather_icon(0) == "clear", "clear weather icon mapping")
    expect(utilities.weather_icon(3) == "cloud", "cloud weather icon mapping")
    expect(utilities.weather_icon(63) == "rain", "rain weather icon mapping")
    expect(utilities.weather_icon(73) == "snow", "snow weather icon mapping")
    expect(utilities.weather_icon(95) == "rain", "thunderstorm remains in safe rain icon class")

    try:
        utilities.weather({"location": "Nowhere Invalid", "day_offset": 0})
    except KadenceUtilityError:
        print("PASS  unknown location fails safely")
    else:
        raise AssertionError("unknown location unexpectedly succeeded")

    web = utilities.web_lookup({"query": "What changed today?"})
    expect(web["answer"] == "Current factual answer.", "web lookup extracts spoken factual answer")
    expect(len(web["sources"]) == 2, "web lookup deduplicates and bounds source list")
    web_call = next(call for call in fake.calls if call["url"] == OPENAI_RESPONSES)
    expect(web_call["method"] == "POST", "web lookup uses fixed POST endpoint")
    expect(web_call["payload"]["input"] == "What changed today?", "web query is data, not a URL")
    expect(web_call["payload"]["tools"] == [{"type": "web_search"}], "only OpenAI web-search tool is requested")
    expect(web_call["payload"]["store"] is False, "web utility disables response storage")

    endpoints = {call["url"] for call in fake.calls}
    expect(
        endpoints <= {OPEN_METEO_GEOCODE, OPEN_METEO_FORECAST, OPENAI_RESPONSES},
        "utility network destinations are fixed allow-listed endpoints",
    )

    no_key = KadenceReadOnlyUtilities(request_json=fake)
    try:
        no_key.web_lookup({"query": "test query"})
    except KadenceUtilityError:
        print("PASS  missing web credential fails visibly")
    else:
        raise AssertionError("missing web credential unexpectedly succeeded")

    print("M6 deterministic utility tests: PASS")


if __name__ == "__main__":
    main()
