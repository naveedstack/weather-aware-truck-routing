"""Open-Meteo client: the request, parsing, caching, the forecast range and error handling."""

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import pytest
import requests
import responses
from urllib3.exceptions import ReadTimeoutError

from trips.clients import openmeteo
from trips.domain.times import epoch_seconds
from trips.domain.weather import WeatherSample
from trips.errors import WeatherRateLimited, WeatherUnavailable

URL = "https://api.open-meteo.com/v1/forecast"
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
START = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
END = START + timedelta(hours=2)
TIMES = [epoch_seconds(START + timedelta(hours=h)) for h in range(3)]


def hourly(wind=(5.0, 6.0, 7.0), rain=(0.0, 0.01, 0.2), showers=(0.0, 0.09, 0.05)):
    return {
        "time": TIMES,
        "wind_speed_10m": list(wind),
        "wind_gusts_10m": [9.0, 9.5, 10.0],
        "rain": list(rain),
        "showers": list(showers),
        "snowfall": [0.0, 0.0, 0.6],
    }


def form_of(call) -> dict[str, list[str]]:
    return parse_qs(call.request.body)


def test_one_post_for_many_locations(http):
    http.post(URL, json=[{"hourly": hourly()}, {"hourly": hourly(wind=(30.0, 31.0, 32.0))}])
    forecasts = openmeteo.fetch_forecasts([(35.22, -101.83), (39.74, -104.99)], START, END, now=NOW)
    form = form_of(http.calls[0])
    assert form["latitude"] == ["35.2200,39.7400"]
    assert form["longitude"] == ["-101.8300,-104.9900"]
    assert form["hourly"] == ["wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"]
    assert form["wind_speed_unit"] == ["mph"]
    assert form["precipitation_unit"] == ["inch"]
    assert form["timeformat"] == ["unixtime"]
    assert form["start_hour"] == ["2026-10-24T15:00"]
    assert form["end_hour"] == ["2026-10-24T17:00"]
    amarillo = forecasts[(35.22, -101.83)]
    assert amarillo[TIMES[1]] == WeatherSample(
        wind_mph=6.0, gust_mph=9.5, rain_in_per_hr=0.1, snow_in_per_hr=0.0
    )
    assert forecasts[(39.74, -104.99)][TIMES[0]].wind_mph == 30.0


def test_a_single_location_answer_is_an_object(http):
    http.post(URL, json={"hourly": hourly()})
    forecasts = openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    assert set(forecasts[(35.22, -101.83)]) == set(TIMES)


def test_missing_values_become_no_data(http):
    http.post(URL, json={"hourly": hourly(wind=(None, 6.0, 7.0))})
    forecast = openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)[(35.22, -101.83)]
    assert forecast[TIMES[0]].wind_mph is None


def test_locations_are_cached(http):
    http.post(URL, json={"hourly": hourly()})
    openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    http.post(URL, json={"hourly": hourly()})
    openmeteo.fetch_forecasts([(35.22, -101.83), (39.74, -104.99)], START, END, now=NOW)
    assert len(http.calls) == 2
    assert form_of(http.calls[1])["latitude"] == ["39.7400"]  # only the new location


def test_requests_stop_at_the_end_of_the_forecast_range(http):
    http.post(URL, json={"hourly": hourly()})
    openmeteo.fetch_forecasts([(35.22, -101.83)], START, START + timedelta(days=30), now=NOW)
    assert form_of(http.calls[0])["end_hour"] == ["2026-11-08T23:00"]  # 16 days from today, minus an hour


def test_nothing_is_requested_past_the_forecast_range(http):
    later = datetime(2026, 11, 20, tzinfo=UTC)
    forecasts = openmeteo.fetch_forecasts([(35.22, -101.83)], later, later + timedelta(hours=5), now=NOW)
    assert forecasts == {(35.22, -101.83): {}}
    assert len(http.calls) == 0


def test_large_requests_are_split(http, monkeypatch):
    monkeypatch.setattr(openmeteo, "MAX_LOCATIONS_PER_REQUEST", 2)
    http.post(URL, json=[{"hourly": hourly()}, {"hourly": hourly()}])
    http.post(URL, json={"hourly": hourly()})
    forecasts = openmeteo.fetch_forecasts([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)], START, END, now=NOW)
    assert len(http.calls) == 2
    assert len(forecasts) == 3


@pytest.mark.parametrize(
    ("reason", "message", "retry_after"),
    [
        ("Minutely API request limit exceeded. Please try again in one minute.", "per-minute limit", 60),
        ("Hourly API request limit exceeded. Please try again in the next hour.", "hourly limit", 3600),
        ("Daily API request limit exceeded. Please try again tomorrow.", "midnight UTC", 12 * 3600),
        ("Too many concurrent requests", "busy", 5),
    ],
)
def test_rate_limits_get_a_clear_message(http, reason, message, retry_after):
    http.post(URL, status=429, json={"error": True, "reason": reason})
    with pytest.raises(WeatherRateLimited) as caught:
        openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    assert message in caught.value.message
    assert caught.value.retry_after_s == retry_after  # NOW is 12:00 UTC: an hour to 13:00, 12 to midnight
    assert len(http.calls) == 1  # a rate limit is never retried; every retry would count again


def test_an_overload_is_retried_once(http, monkeypatch):
    monkeypatch.setattr(openmeteo, "RETRY_DELAY_S", 0)
    http.post(URL, status=503, json={"error": True, "reason": "The service is overloaded"})
    http.post(URL, json={"hourly": hourly()})
    assert openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    assert len(http.calls) == 2


def test_a_second_overload_is_an_error(http, monkeypatch):
    monkeypatch.setattr(openmeteo, "RETRY_DELAY_S", 0)
    http.post(URL, status=503, json={"error": True, "reason": "The service is overloaded"})
    http.post(URL, status=503, json={"error": True, "reason": "The service is overloaded"})
    with pytest.raises(WeatherUnavailable, match="overloaded"):
        openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"error": True, "reason": "Parameter 'end_hour' is out of allowed range"}),
        (200, "Unexpected error while streaming data"),
        (200, [{"hourly": hourly()}]),  # one result for two locations
        (200, [{"hourly": {"time": TIMES}}, {"hourly": {"time": TIMES}}]),
    ],
)
def test_bad_answers_are_errors(http, status, body):
    if isinstance(body, str):
        http.post(URL, status=status, body=body)
    else:
        http.post(URL, status=status, json=body)
    with pytest.raises(WeatherUnavailable):
        openmeteo.fetch_forecasts([(35.22, -101.83), (39.74, -104.99)], START, END, now=NOW)


def test_timeouts_are_errors(http):
    http.post(URL, body=requests.Timeout())
    with pytest.raises(WeatherUnavailable, match="took too long"):
        openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)


def test_last_forecast_hour():
    assert openmeteo.last_forecast_hour(NOW) == datetime(2026, 11, 8, 23, 0, tzinfo=UTC)


def test_a_dropped_connection_is_retried_once(http, monkeypatch):
    monkeypatch.setattr(openmeteo, "RETRY_DELAY_S", 0)
    http.post(URL, body=requests.ConnectionError("Connection reset by peer"))
    http.post(URL, json={"hourly": hourly()})
    assert openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    assert len(http.calls) == 2


def test_two_dropped_connections_are_an_error(http, monkeypatch):
    monkeypatch.setattr(openmeteo, "RETRY_DELAY_S", 0)
    http.post(URL, body=requests.ConnectionError("Connection reset by peer"))
    http.post(URL, body=requests.ConnectionError("Connection reset by peer"))
    with pytest.raises(WeatherUnavailable, match="Couldn't reach"):
        openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)


class StalledResponse:
    """A 200 whose body stops arriving partway, as requests reports it."""

    status_code = 200

    @property
    def content(self):
        raise requests.ConnectionError(ReadTimeoutError(None, None, "Read timed out."))


def test_an_answer_that_stalls_partway_is_not_sent_again(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return StalledResponse()

    monkeypatch.setattr(openmeteo.session(), "post", post)
    with pytest.raises(WeatherUnavailable, match="took too long"):
        openmeteo.fetch_forecasts([(35.22, -101.83)], START, END, now=NOW)
    assert len(calls) == 1  # Open-Meteo already counted it
    assert calls[0]["stream"] is True


def test_overlapping_fetches_share_what_the_first_one_got(http):
    def slow_answer(request):
        time.sleep(0.3)
        count = len(parse_qs(request.body)["latitude"][0].split(","))
        items = [{"hourly": hourly()} for _ in range(count)]
        return 200, {}, json.dumps(items if count > 1 else items[0])

    http.add_callback(responses.POST, URL, callback=slow_answer)
    first = threading.Thread(
        target=openmeteo.fetch_forecasts, args=([(1.0, 1.0), (2.0, 2.0)], START, END), kwargs={"now": NOW}
    )
    first.start()
    time.sleep(0.1)  # the second plan arrives while the first one's request is still running
    openmeteo.fetch_forecasts([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)], START, END, now=NOW)
    first.join()
    assert [form_of(call)["latitude"] for call in http.calls] == [["1.0000,2.0000"], ["3.0000"]]
