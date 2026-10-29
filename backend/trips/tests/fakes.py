"""Fake TomTom and Open-Meteo services for tests, answering at the HTTP level (via `responses`).

Routes come from trimmed real TomTom responses for Dallas -> Denver (tests/fixtures). Weather comes
from a rule: a function of (latitude, longitude, epoch hour) returning Open-Meteo's hourly values.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import requests
import responses

FIXTURES = Path(__file__).parent / "fixtures"
DALLAS = (32.77798, -96.79622)
DENVER = (39.73845, -104.98486)
AMARILLO_BOX = ((34.9, -102.2), (35.6, -101.4))  # only TomTom's alternative route passes it
SALINA_BOX = ((38.6, -97.9), (39.1, -97.3))  # the main and the via routes pass it

WeatherRule = Callable[[float, float, int], dict[str, float | None]]


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def calm(lat: float, lon: float, epoch: int) -> dict[str, float | None]:
    return {"wind_speed_10m": 5.0, "wind_gusts_10m": 9.0, "rain": 0.0, "showers": 0.0, "snowfall": 0.0}


def windy_in(
    box: tuple[tuple[float, float], tuple[float, float]], mph: float = 50.0, hours: set[int] | None = None
):
    """Calm weather, except `mph` sustained wind inside the box (during `hours`, if given)."""
    (south, west), (north, east) = box

    def rule(lat: float, lon: float, epoch: int) -> dict[str, float | None]:
        values = calm(lat, lon, epoch)
        if south <= lat <= north and west <= lon <= east and (hours is None or epoch in hours):
            values["wind_speed_10m"] = mph
        return values

    return rule


class FakeServices:
    """Register on a responses.RequestsMock; records what was asked."""

    def __init__(self, mock: responses.RequestsMock) -> None:
        self.weather: WeatherRule = calm
        self.places = {"dallas, tx": ("Dallas, TX", DALLAS), "denver, co": ("Denver, CO", DENVER)}
        self.main_routes = fixture("tomtom_dallas_denver.json")
        self.via_routes = fixture("tomtom_dallas_denver_via.json")
        self.via_delay_s = 0.0
        self.alternatives_time_out = False  # the request with maxAlternatives=2 times out
        self.via_error: tuple[int, dict] | None = None  # (status, body) for every via request
        self.route_requests: list[str] = []
        self.weather_requests: list[dict[str, list[str]]] = []
        mock.add_callback(
            responses.GET, re.compile(r"https://api\.tomtom\.com/search/2/geocode/.+"), self._geocode
        )
        mock.add_callback(
            responses.GET, re.compile(r"https://api\.tomtom\.com/routing/1/calculateRoute/.+"), self._route
        )
        mock.add_callback(responses.POST, "https://api.open-meteo.com/v1/forecast", self._forecast)

    @property
    def weather_locations(self) -> int:
        return sum(len(form["latitude"][0].split(",")) for form in self.weather_requests)

    def _geocode(self, request) -> tuple[int, dict, str]:
        query = unquote(urlsplit(request.url).path.rsplit("/", 1)[-1].removesuffix(".json"))
        match = self.places.get(" ".join(query.split()).casefold())
        results = []
        if match:
            name, (lat, lon) = match
            results = [
                {
                    "type": "Geography",
                    "address": {"freeformAddress": name},
                    "position": {"lat": lat, "lon": lon},
                }
            ]
        return 200, {}, json.dumps({"summary": {"numResults": len(results)}, "results": results})

    @property
    def via_requests(self) -> list[str]:
        return [url for url in self.route_requests if "circle(" in url]

    def _route(self, request) -> tuple[int, dict, str]:
        url = unquote(request.url)
        self.route_requests.append(url)
        if "circle(" in url:
            time.sleep(self.via_delay_s)
            if self.via_error:
                status, body = self.via_error
                return status, {}, json.dumps(body)
            return 200, {}, json.dumps(self.via_routes)
        alternatives = int(parse_qs(urlsplit(url).query)["maxAlternatives"][0])
        if self.alternatives_time_out and alternatives > 0:
            raise requests.ReadTimeout("Read timed out.")
        # Like TomTom: the main route plus at most `alternatives` others.
        return (
            200,
            {},
            json.dumps({**self.main_routes, "routes": self.main_routes["routes"][: alternatives + 1]}),
        )

    def _forecast(self, request) -> tuple[int, dict, str]:
        body = request.body.decode() if isinstance(request.body, bytes) else request.body
        form = parse_qs(body)
        self.weather_requests.append(form)
        lats = [float(v) for v in form["latitude"][0].split(",")]
        lons = [float(v) for v in form["longitude"][0].split(",")]
        start = _epoch(form["start_hour"][0])
        end = _epoch(form["end_hour"][0])
        times = list(range(start, end + 1, 3600))
        items = []
        for lat, lon in zip(lats, lons, strict=True):
            hourly: dict[str, list] = {"time": times}
            for moment in times:
                for name, value in self.weather(lat, lon, moment).items():
                    hourly.setdefault(name, []).append(value)
            items.append({"latitude": lat, "longitude": lon, "hourly": hourly})
        return 200, {}, json.dumps(items if len(items) > 1 else items[0])


def _epoch(hour: str) -> int:
    return int(datetime.strptime(hour, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).timestamp())
