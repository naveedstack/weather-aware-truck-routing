"""Turning raw forecast values into risk inputs."""

import math

import pytest

from trips.domain.risk import RiskLevel
from trips.domain.weather import WeatherSample, assess_sample, location_key, make_sample


def sample(wind=0.0, gust=0.0, rain=0.0, showers=0.0, snow=0.0):
    return make_sample(wind_mph=wind, gust_mph=gust, rain_in=rain, showers_in=showers, snowfall_in=snow)


@pytest.mark.parametrize(
    ("rain", "showers", "expected"),
    [
        (0.01, 0.09, 0.1),  # 0.01 + 0.09 is 0.09999999999999999 in floating point
        (0.009, 0.091, 0.1),
        (0.026, 0.074, 0.1),
        (0.15, 0.10, 0.25),
        (0.45, 0.05, 0.5),
        (0.7, 0.3, 1.0),
        (0.7, 0.301, 1.001),
        (0.0, 0.0, 0.0),
    ],
)
def test_rain_is_rain_plus_showers_without_float_noise(rain, showers, expected):
    assert sample(rain=rain, showers=showers).rain_in_per_hr == expected


def test_boundary_sums_classify_at_the_boundary():
    assert assess_sample(sample(rain=0.01, showers=0.09), 0).rain is RiskLevel.MODERATE
    assert assess_sample(sample(rain=0.7, showers=0.3), 0).rain is RiskLevel.SEVERE
    assert assess_sample(sample(rain=0.7, showers=0.301), 0).rain is RiskLevel.NO_TRAVEL


def test_values_are_rounded_to_api_precision():
    rounded = sample(wind=24.96, gust=30.04, rain=0.1234, snow=0.4996)
    assert rounded.wind_mph == 25.0
    assert rounded.gust_mph == 30.0
    assert rounded.rain_in_per_hr == 0.123
    assert rounded.snow_in_per_hr == 0.5


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -0.01, "abc", True])
def test_unusable_values_are_missing(bad):
    assert sample(wind=bad, gust=bad, rain=bad, snow=bad) == WeatherSample(None, None, None, None)


def test_rain_is_missing_when_either_part_is_missing():
    assert sample(rain=0.05, showers=None).rain_in_per_hr is None
    assert sample(rain=None, showers=0.05).rain_in_per_hr is None


def test_numeric_strings_are_accepted():
    assert sample(wind="12.5", rain="0.010").wind_mph == 12.5


def test_gusts_never_change_the_level():
    assert assess_sample(sample(wind=20, gust=80), 0).level is RiskLevel.LOW


def test_missing_sample_is_no_data():
    assert assess_sample(None, 0).level is None


def test_assess_sample_uses_the_load():
    windy = sample(wind=47, gust=60)
    assert assess_sample(windy, 35_000).level is RiskLevel.NO_TRAVEL
    assert assess_sample(windy, 25_000).level is RiskLevel.SEVERE


def test_location_key_rounds_to_about_a_kilometre():
    assert location_key((35.22187, -101.83129)) == (35.22, -101.83)
    assert location_key((35.2249, -101.8251)) == (35.22, -101.83)
