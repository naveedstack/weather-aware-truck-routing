"""Hourly weather values in the units the risk rules use, and how to assess them."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from .geo import LatLon
from .risk import NO_DATA, Assessment, assess, leading_condition

# Forecast locations are rounded to 0.01° (about 1 km). Open-Meteo's finest US model has a 3 km
# grid, so this loses nothing, and checkpoints shared by overlapping routes become one location.
LOCATION_DECIMALS = 2

# Open-Meteo returns wind with 1 decimal (mph) and precipitation with 3 decimals (inch).
# Rounding to the same precision removes float noise, e.g. 0.01 + 0.09 = 0.09999999999999999,
# which would otherwise read as Low instead of Moderate.
WIND_DECIMALS = 1
PRECIPITATION_DECIMALS = 3


def location_key(point: LatLon) -> LatLon:
    """The forecast location used for a point."""
    return (round(point[0], LOCATION_DECIMALS), round(point[1], LOCATION_DECIMALS))


@dataclass(frozen=True)
class WeatherSample:
    """Weather at one place for one forecast hour. ``None`` means the value is missing."""

    wind_mph: float | None  # sustained wind at 10 m
    gust_mph: float | None  # shown for information only
    rain_in_per_hr: float | None  # rain + showers over the hour
    snow_in_per_hr: float | None  # snowfall over the hour


def _clean(value: object, decimals: int) -> float | None:
    """A finite, non-negative number rounded to the API's precision, or None if unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, decimals)


def make_sample(
    *,
    wind_mph: object,
    gust_mph: object,
    rain_in: object,
    showers_in: object,
    snowfall_in: object,
) -> WeatherSample:
    """Build a sample from raw hourly values: mph, and inches that fell during the hour.

    The liquid rain rate is rain plus showers; if either part is missing, rain is missing.
    """
    rain = _clean(rain_in, PRECIPITATION_DECIMALS)
    showers = _clean(showers_in, PRECIPITATION_DECIMALS)
    return WeatherSample(
        wind_mph=_clean(wind_mph, WIND_DECIMALS),
        gust_mph=_clean(gust_mph, WIND_DECIMALS),
        rain_in_per_hr=(
            None if rain is None or showers is None else round(rain + showers, PRECIPITATION_DECIMALS)
        ),
        snow_in_per_hr=_clean(snowfall_in, PRECIPITATION_DECIMALS),
    )


# A location's forecast: one sample per UTC hour, keyed by the hour's epoch seconds.
Forecast = Mapping[int, WeatherSample]


def assess_sample(sample: WeatherSample | None, load_lb: float) -> Assessment:
    """Risk for one sample with the given load. A missing sample is "No data"."""
    if sample is None:
        return NO_DATA
    return assess(sample.wind_mph, sample.rain_in_per_hr, sample.snow_in_per_hr, load_lb)


def leading_reading(sample: WeatherSample | None, assessment: Assessment) -> float | None:
    """The value of the condition that set the level, in that condition's own unit (mph for wind,
    inches per hour for rain and snow). None when nothing set a level."""
    cause = leading_condition(assessment)
    if sample is None or cause is None:
        return None
    return {
        "wind": sample.wind_mph,
        "rain": sample.rain_in_per_hr,
        "snow": sample.snow_in_per_hr,
    }[cause]
