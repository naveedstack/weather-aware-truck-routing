"""POST /api/plan/: validation, the response shape and error responses (fake upstream services)."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from trips import planner, views
from trips.errors import WeatherRateLimited

from .fakes import AMARILLO_BOX, windy_in


def departure(hours_ahead=2.0) -> str:
    moment = datetime.now(UTC) + timedelta(hours=hours_ahead)
    return moment.replace(microsecond=0).isoformat()


def form(**changes):
    body = {"origin": "Dallas, TX", "destination": "Denver, CO", "departure": departure(), "load_lb": 35_000}
    body.update(changes)
    return {key: value for key, value in body.items() if value is not None}


def post(client, body):
    return client.post("/api/plan/", data=json.dumps(body), content_type="application/json")


def test_plan_response(client, services):
    services.weather = windy_in(AMARILLO_BOX, mph=50)
    response = post(client, form())
    assert response.status_code == 200
    data = response.json()

    assert data["origin"] == {"query": "Dallas, TX", "name": "Dallas, TX", "lat": 32.77798, "lon": -96.79622}
    assert data["interval_mi"] == 25
    assert [route["id"] for route in data["routes"]] == ["A", "B", "C"]
    assert data["recommendation"]["route_id"] == "A"
    assert [route["recommended"] for route in data["routes"]] == [True, False, False]
    assert data["routes"][1]["unsafe"] is True
    assert data["routes"][1]["miles"]["no_travel"] > 0

    route = data["routes"][0]
    assert set(route["miles"]) == {"no_travel", "severe", "high", "moderate", "low", "no_data"}
    assert sum(route["miles"].values()) == pytest.approx(route["distance_mi"], abs=0.5)
    lon, lat = route["line"][0]  # GeoJSON order
    assert (lat, lon) == (32.77798, -96.79622)

    checkpoint = route["checkpoints"][1]
    assert checkpoint["mile"] == 25.0
    assert checkpoint["eta"].endswith("Z")
    assert checkpoint["forecast_hour"].endswith(":00:00Z")
    assert checkpoint["risk"] == 0
    assert checkpoint["wind_mph"] == 5.0
    assert checkpoint["gust_mph"] == 9.0
    assert checkpoint["load_rule"] is None

    stormy = [cp for cp in data["routes"][1]["checkpoints"] if cp["risk"] == 4]
    assert stormy
    assert stormy[0]["wind_risk"] == 4
    assert stormy[0]["load_rule"] == "Wind of 45 up to 55 mph with a load over 30,000 lb is No Travel."

    heatmap = data["heatmap"]
    assert len(heatmap["hours"]) == 49
    assert heatmap["cells"]
    assert all(
        len(cell["levels"]) == 49 and set(cell["levels"]) <= set("01234-") for cell in heatmap["cells"]
    )
    # One cause character per hour, so the UI can say why a cell has its colour.
    assert all(len(cell["causes"]) == 49 and set(cell["causes"]) <= set("wrs-") for cell in heatmap["cells"])
    # One value slot per hour, filled only where the level is Moderate or worse.
    assert all(len(cell["values"].split(",")) == 49 for cell in heatmap["cells"])
    west, south, east, north = heatmap["cells"][0]["bounds"]  # GeoJSON bbox order
    assert north - south == pytest.approx(heatmap["cell_size_deg"])
    assert east - west == pytest.approx(heatmap["cell_size_deg"])
    assert data["weather_locations"] <= 300


def test_a_departure_with_seconds_is_rounded_to_the_minute(client, services):
    start = (datetime.now(UTC) + timedelta(hours=3)).replace(minute=29, second=45, microsecond=0)
    data = post(client, form(departure=start.isoformat())).json()
    rounded = start.replace(minute=30, second=0)
    assert datetime.fromisoformat(data["departure"]) == rounded
    first = data["routes"][0]["checkpoints"][0]
    assert first["eta"] == data["departure"]
    assert first["forecast_hour"] == data["heatmap"]["hours"][0]  # hour 0 is the start's forecast hour


def test_arrival_is_the_departure_plus_the_shown_travel_time(client, services):
    start = (datetime.now(UTC) + timedelta(hours=2)).replace(second=0, microsecond=0)
    data = post(client, form(departure=start.isoformat())).json()
    for route in data["routes"]:
        assert datetime.fromisoformat(route["arrival"]) == start + timedelta(minutes=route["travel_time_min"])
        assert route["checkpoints"][-1]["eta"] == route["arrival"]
        assert all(checkpoint["eta"].endswith(":00Z") for checkpoint in route["checkpoints"])


@pytest.mark.parametrize(
    ("changes", "field", "message"),
    [
        ({"origin": None}, "origin", "required"),
        ({"origin": "   "}, "origin", "blank"),
        ({"destination": "x" * 201}, "destination", "200"),
        ({"destination": " DALLAS,  tx "}, "destination", "same"),
        ({"departure": "2026-10-25T08:00:00"}, "departure", "time zone offset"),
        ({"departure": "tomorrow"}, "departure", "format"),
        ({"departure": "2020-01-01T08:00:00Z"}, "departure", "past"),
        ({"departure": "2099-01-01T08:00:00Z"}, "departure", "end of the weather forecast"),
        ({"departure": "9999-12-31T23:00:00-05:00"}, "departure", "out of range"),
        ({"load_lb": -1}, "load_lb", "greater than or equal to 0"),
        ({"load_lb": 80_001}, "load_lb", "less than or equal to 80000"),
        ({"load_lb": "heavy"}, "load_lb", "valid number"),
        ({"load_lb": "nan"}, "load_lb", "valid number"),
        ({"load_lb": True}, "load_lb", "valid number"),
        ({"interval_mi": 15}, "interval_mi", "not a valid choice"),
    ],
)
def test_invalid_input(client, services, changes, field, message):
    response = post(client, form(**changes))
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_input"
    assert message in error["fields"][field]


def test_departure_a_few_minutes_ago_is_accepted(client, services):
    assert post(client, form(departure=departure(hours_ahead=-0.1))).status_code == 200


def test_interval_defaults_to_25_and_accepts_strings(client, services):
    assert post(client, form()).json()["interval_mi"] == 25
    assert post(client, form(interval_mi="10")).json()["interval_mi"] == 10


def test_plan_errors_keep_their_status_and_message(client, services):
    response = post(client, form(origin="Nowhere, ZZ"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "place_not_found"
    assert response.json()["error"]["field"] == "origin"


def test_rate_limits_say_when_to_retry(client, services, monkeypatch):
    def rate_limited(*args, **kwargs):
        raise WeatherRateLimited("The free weather service's per-minute limit was reached.", retry_after_s=60)

    monkeypatch.setattr(planner.openmeteo, "fetch_forecasts", rate_limited)
    response = post(client, form())
    assert response.status_code == 503
    assert response["Retry-After"] == "60"
    assert response.json()["error"]["code"] == "weather_rate_limited"


def test_unexpected_failures_are_json(client, services, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(views, "plan_trip", broken)
    response = post(client, form())
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong while planning the trip."}
    }


def test_malformed_json_uses_the_error_shape(client):
    response = client.post("/api/plan/", data="{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"


def test_wrong_method_uses_the_error_shape(client):
    response = client.get("/api/plan/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_departure_offsets_are_planned_in_utc(client, services):
    local = (datetime.now(UTC) + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    local = local.astimezone(timezone(timedelta(hours=-5)))
    data = post(client, form(departure=local.isoformat())).json()
    utc = local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    first = data["routes"][0]["checkpoints"][0]
    assert data["departure"] == first["eta"] == first["forecast_hour"] == data["heatmap"]["hours"][0] == utc


def test_a_body_that_is_not_an_object_gets_a_message_not_field_errors(client):
    response = client.post("/api/plan/", data="[]", content_type="application/json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["message"] == "Invalid data. Expected a dictionary, but got list."
    assert error["fields"] == {}


def test_no_route_errors_name_both_places_and_no_field(client, services):
    services.main_routes = {"routes": []}
    error = post(client, form()).json()["error"]
    assert error == {"code": "no_route", "message": "No truck route found between Dallas, TX and Denver, CO."}


def test_each_condition_has_its_own_level_in_the_json(client, services):
    services.weather = lambda lat, lon, epoch: {
        "wind_speed_10m": 30.0, "wind_gusts_10m": 40.0, "rain": 0.2, "showers": 0.1, "snowfall": 0.6
    }  # fmt: skip
    checkpoint = post(client, form()).json()["routes"][0]["checkpoints"][0]
    assert (checkpoint["wind_mph"], checkpoint["rain_in_per_hr"], checkpoint["snow_in_per_hr"]) == (
        30.0,
        0.3,
        0.6,
    )
    assert (checkpoint["wind_risk"], checkpoint["rain_risk"], checkpoint["snow_risk"]) == (1, 2, 1)
    assert checkpoint["risk"] == 2


def test_heatmap_cells_say_which_condition_set_each_level(client, services):
    services.weather = lambda lat, lon, epoch: {
        "wind_speed_10m": 5.0, "wind_gusts_10m": 8.0, "rain": 0.3, "showers": 0.0, "snowfall": 0.0
    }  # fmt: skip

    cells = post(client, form()).json()["heatmap"]["cells"]

    # Rain of 0.30 in/hr is High everywhere, and rain is what caused it.
    assert all(set(cell["levels"]) == {"2"} for cell in cells)
    assert all(set(cell["causes"]) == {"r"} for cell in cells)
    # High is above Moderate, so every hour carries the rain rate behind it.
    assert all(set(cell["values"].split(",")) == {"0.3"} for cell in cells)


def test_low_heatmap_cells_carry_no_reading(client, services):
    """Calm is Low everywhere, the UI says nothing about a Low cell, so no reading is sent."""
    cells = post(client, form()).json()["heatmap"]["cells"]

    assert all(set(cell["levels"]) <= {"0", "-"} for cell in cells)
    assert all(set(cell["values"].split(",")) == {""} for cell in cells)
