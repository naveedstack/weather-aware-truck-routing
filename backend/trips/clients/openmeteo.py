"""Open-Meteo hourly forecasts for many locations in one request (free tier, no key)."""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from itertools import batched
from typing import Any

import requests
from django.core.cache import cache

from ..domain.geo import LatLon
from ..domain.times import HOUR, epoch_seconds
from ..domain.weather import Forecast, WeatherSample, make_sample
from ..errors import WeatherRateLimited, WeatherUnavailable
from .http import CONNECT_TIMEOUT_S, is_timeout, session

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
FORECAST_DAYS = 16  # Open-Meteo forecasts up to 16 days from the start of today (UTC)
MAX_LOCATIONS_PER_REQUEST = 1000
TIMEOUT_S = 10.0
RETRY_DELAY_S = 1.0
CACHE_S = 30 * 60  # the US models behind Open-Meteo refresh hourly

# Open-Meteo answers one request per IP at a time and rejects some extras, so this process sends
# its requests one after another.
_one_at_a_time = threading.Lock()

_RATE_LIMIT_MESSAGES = {
    "minute": "The free weather service's per-minute limit was reached. Please try again in a minute.",
    "hour": "The free weather service's hourly limit was reached. Please try again in the next hour.",
    "day": "The free weather service's daily limit was reached. It resets at midnight UTC.",
    "concurrent": "The free weather service is busy. Please try again in a few seconds.",
}


def last_forecast_hour(now: datetime) -> datetime:
    """The latest hour Open-Meteo has a forecast for."""
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=FORECAST_DAYS) - HOUR


def _cache_key(location: LatLon, start: datetime, end: datetime) -> str:
    return f"openmeteo:{location[0]:.4f},{location[1]:.4f}:{epoch_seconds(start)}:{epoch_seconds(end)}"


def _cached(keys: dict[LatLon, str], locations: Iterable[LatLon]) -> dict[LatLon, Forecast]:
    locations = list(locations)
    found = cache.get_many([keys[location] for location in locations])
    return {location: found[keys[location]] for location in locations if keys[location] in found}


def fetch_forecasts(
    locations: Iterable[LatLon], start: datetime, end: datetime, *, now: datetime | None = None
) -> dict[LatLon, Forecast]:
    """Hourly samples for every location, for the whole UTC hours from start to end inclusive.

    Hours past Open-Meteo's range are left out, so they read as "No data". Locations are cached
    per instance; the location budget never relies on that.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    wanted = sorted(set(locations))
    end = min(end, last_forecast_hour(now))
    if not wanted or start > end:
        return {location: {} for location in wanted}

    keys = {location: _cache_key(location, start, end) for location in wanted}
    forecasts = _cached(keys, wanted)
    fetched = 0
    if len(forecasts) < len(wanted):
        with _one_at_a_time:
            # Another plan may have fetched some of these while this one waited for its turn.
            forecasts.update(_cached(keys, (location for location in wanted if location not in forecasts)))
            missing = [location for location in wanted if location not in forecasts]
            for chunk in batched(missing, MAX_LOCATIONS_PER_REQUEST):
                new = _request(chunk, start, end, now)
                cache.set_many({keys[location]: forecast for location, forecast in new.items()}, CACHE_S)
                forecasts.update(new)
                fetched += len(new)
    logger.info(
        "Forecasts for %d locations: %d fetched, %d cached", len(wanted), fetched, len(wanted) - fetched
    )
    return forecasts


def _request(
    chunk: Sequence[LatLon], start: datetime, end: datetime, now: datetime
) -> dict[LatLon, Forecast]:
    form = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
        "hourly": ",".join(HOURLY_VARIABLES),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timeformat": "unixtime",
        "start_hour": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M"),
    }
    response = _post(form, now)
    try:
        body = response.json()
    except ValueError:
        # Open-Meteo streams its answer, so a failure halfway leaves a 200 with broken JSON.
        logger.warning("Open-Meteo returned invalid JSON for %d locations", len(chunk))
        raise WeatherUnavailable("The weather service sent an unreadable answer. Please try again.") from None
    items = body if isinstance(body, list) else [body]
    if len(items) != len(chunk):
        logger.warning("Open-Meteo returned %d results for %d locations", len(items), len(chunk))
        raise WeatherUnavailable("The weather service sent an incomplete answer. Please try again.")
    try:
        return {location: _parse_hourly(item["hourly"]) for location, item in zip(chunk, items, strict=True)}
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("Unexpected Open-Meteo data: %r", error)
        raise WeatherUnavailable("The weather service sent an unreadable answer. Please try again.") from None


def _post(form: dict[str, str], now: datetime) -> requests.Response:
    """POST the form (no URL length limit) and read the whole answer.

    A dropped connection or an overload (503) is retried once after a short pause; Open-Meteo
    doesn't count those. Nothing is retried once an answer has started to arrive, because by then
    Open-Meteo has counted every location in the request.
    """
    for attempt in (1, 2):
        try:
            response = session().post(
                FORECAST_URL, data=form, timeout=(CONNECT_TIMEOUT_S, TIMEOUT_S), stream=True
            )
        except requests.RequestException as error:
            logger.warning("Open-Meteo request failed (attempt %d): %s", attempt, error)
            if is_timeout(error):
                raise WeatherUnavailable(
                    "The weather service took too long to answer. Please try again."
                ) from None
            if attempt == 2:
                raise WeatherUnavailable("Couldn't reach the weather service. Please try again.") from None
        else:
            if response.status_code != 503 or attempt == 2:
                _read_body(response)
                if response.status_code == 200:
                    return response
                raise _error_for(response, now)
            response.close()
            logger.warning("Open-Meteo overloaded (503); retrying once")
        time.sleep(RETRY_DELAY_S)
    raise AssertionError("unreachable")


def _read_body(response: requests.Response) -> None:
    try:
        response.content  # noqa: B018 - reads the rest of the streamed body
    except requests.RequestException as error:
        logger.warning("Open-Meteo stopped answering partway: %s", error)
        if is_timeout(error):
            raise WeatherUnavailable(
                "The weather service took too long to answer. Please try again."
            ) from None
        raise WeatherUnavailable("The weather service stopped answering partway. Please try again.") from None


def _retry_after_s(kind: str, now: datetime) -> int:
    """Seconds until a limit of this kind resets. Open-Meteo's counters follow the UTC clock."""
    if kind == "hour":
        reset = now.replace(minute=0, second=0, microsecond=0) + HOUR
    elif kind == "day":
        reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        return 60 if kind == "minute" else 5
    return max(1, math.ceil((reset - now).total_seconds()))


def _error_for(response: requests.Response, now: datetime) -> Exception:
    try:
        reason = str(response.json().get("reason", ""))
    except ValueError:
        reason = response.text[:200]
    logger.warning("Open-Meteo error %s: %s", response.status_code, reason)
    if response.status_code == 429:
        # Reasons look like "Minutely API request limit exceeded. ..." or "Too many concurrent requests".
        lowered = reason.lower()
        words = (("minutely", "minute"), ("hourly", "hour"), ("daily", "day"), ("concurrent", "concurrent"))
        kind = next((kind for word, kind in words if word in lowered), "minute")
        return WeatherRateLimited(_RATE_LIMIT_MESSAGES[kind], retry_after_s=_retry_after_s(kind, now))
    if response.status_code == 503:
        return WeatherUnavailable("The weather service is overloaded. Please try again shortly.")
    return WeatherUnavailable(
        f"The weather service couldn't handle this request (error {response.status_code})."
    )


def _parse_hourly(hourly: dict[str, Any]) -> Forecast:
    times = hourly["time"]
    columns = [hourly[name] for name in HOURLY_VARIABLES]
    if any(len(column) != len(times) for column in columns):
        raise ValueError("hourly columns have different lengths")
    forecast: dict[int, WeatherSample] = {}
    for index, moment in enumerate(times):
        wind, gust, rain, showers, snow = (column[index] for column in columns)
        forecast[int(moment)] = make_sample(
            wind_mph=wind, gust_mph=gust, rain_in=rain, showers_in=showers, snowfall_in=snow
        )
    return forecast
