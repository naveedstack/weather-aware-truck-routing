"""TomTom client: request parameters, response parsing and error handling (no real HTTP)."""

import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests
from urllib3.exceptions import ReadTimeoutError

from trips.clients import tomtom
from trips.errors import NoRoute, PlaceNotFound, RoutingTimeout, RoutingUnavailable

from .fakes import DALLAS, DENVER, fixture

GEOCODE = re.compile(r"https://api\.tomtom\.com/search/2/geocode/.+")
SEARCH = re.compile(r"https://api\.tomtom\.com/search/2/search/.+")
ROUTE = re.compile(r"https://api\.tomtom\.com/routing/1/calculateRoute/.+")
DEPARTURE = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)


def query_of(call) -> dict[str, list[str]]:
    return parse_qs(urlsplit(call.request.url).query)


def test_geocode_returns_the_top_match(http):
    body = {
        "results": [{"address": {"freeformAddress": "Dallas, TX"}, "position": {"lat": 32.78, "lon": -96.8}}]
    }
    http.get(GEOCODE, json=body)
    place = tomtom.geocode("  Dallas,   TX ", "origin")
    assert place == tomtom.Place("Dallas, TX", (32.78, -96.8))
    url = http.calls[0].request.url
    assert urlsplit(url).path == "/search/2/geocode/Dallas%2C%20TX.json"
    assert query_of(http.calls[0])["limit"] == ["1"]
    assert query_of(http.calls[0])["countrySet"] == ["US,CA,MX"]
    assert query_of(http.calls[0])["key"] == ["test-key"]


def test_geocode_results_are_cached(http):
    body = {
        "results": [{"address": {"freeformAddress": "Dallas, TX"}, "position": {"lat": 32.78, "lon": -96.8}}]
    }
    http.get(GEOCODE, json=body)
    tomtom.geocode("Dallas, TX", "origin")
    tomtom.geocode("dallas, tx", "destination")
    assert len(http.calls) == 1


def test_unknown_place(http):
    http.get(GEOCODE, json={"summary": {"numResults": 0}, "results": []})
    with pytest.raises(PlaceNotFound) as caught:
        tomtom.geocode("Xyzzyville", "destination")
    assert caught.value.field == "destination"
    assert "Xyzzyville" in caught.value.message


def city(name: str, region: str, freeform: str | None = None) -> dict:
    """A city in TomTom's search results."""
    address = {
        "municipality": name,
        "countrySubdivision": region,
        "freeformAddress": freeform or f"{name}, {region}",
    }
    return {"type": "Geography", "entityType": "Municipality", "address": address}


def test_suggestions_are_cities_best_match_first(http):
    results = [
        city("Dallas", "TX"),
        city("Dallas", "TX"),
        city("Dale", "VA"),
        city("Toronto", "ON", "Toronto ON"),
    ]
    http.get(SEARCH, json={"results": results})

    # Duplicates are dropped, and every name has the comma, Canadian ones too.
    assert tomtom.suggest_places("  Dal ") == ["Dallas, TX", "Dale, VA", "Toronto, ON"]
    call = http.calls[0]
    assert urlsplit(call.request.url).path == "/search/2/search/Dal.json"
    params = query_of(call)
    assert params["typeahead"] == ["true"]  # the last word may be unfinished
    assert params["idxSet"] == ["Geo"]
    assert params["entityTypeSet"] == ["Municipality"]
    assert params["countrySet"] == ["US,CA,MX"]  # where places are geocoded
    assert params["key"] == ["test-key"]


def test_suggestions_are_five_at_most_and_use_the_address_when_its_parts_are_missing(http):
    results = [{"address": {"freeformAddress": "Dalhart, TX"}}, {"address": {}}]
    results += [city(f"Town {number}", "TX") for number in range(6)]
    http.get(SEARCH, json={"results": results})

    assert tomtom.suggest_places("Dal") == [
        "Dalhart, TX",
        "Town 0, TX",
        "Town 1, TX",
        "Town 2, TX",
        "Town 3, TX",
    ]


def test_suggestions_are_cached(http):
    http.get(SEARCH, json={"results": [city("Dallas", "TX")]})
    tomtom.suggest_places("Dall")
    tomtom.suggest_places("  dall ")
    assert len(http.calls) == 1


def test_suggestion_errors_are_place_search_errors(http):
    http.get(SEARCH, status=429, json={"error": {"description": "Too many requests"}})
    with pytest.raises(RoutingUnavailable, match="place search service is busy"):
        tomtom.suggest_places("Dal")


def test_routes_request_parameters(http):
    http.get(ROUTE, json=fixture("tomtom_dallas_denver.json"))
    tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=2, timeout_s=15)
    call = http.calls[0]
    assert "/routing/1/calculateRoute/32.777980,-96.796220:39.738450,-104.984860/json" in call.request.url
    params = query_of(call)
    assert params["travelMode"] == ["truck"]
    assert params["vehicleCommercial"] == ["true"]
    assert params["departAt"] == ["2026-10-24T15:00:00+00:00"]
    assert params["maxAlternatives"] == ["2"]
    assert params["extendedRouteRepresentation"] == ["distance", "travelTime"]
    assert "vehicleWeight" not in params  # the load is used for the risk rules only


def test_via_point_is_a_circle_waypoint(http):
    http.get(ROUTE, json=fixture("tomtom_dallas_denver_via.json"))
    tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=0, timeout_s=5, via=(37.5, -97.25))
    path = unquote(urlsplit(http.calls[0].request.url).path)
    assert ":circle(37.500000,-97.250000,15000):" in path


def test_routes_follow_tomtom_progress_timing(http):
    data = fixture("tomtom_dallas_denver.json")
    http.get(ROUTE, json=data)
    profiles = tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=2, timeout_s=15)
    assert len(profiles) == 2
    main, raw = profiles[0], data["routes"][0]
    assert main.length_m == pytest.approx(raw["summary"]["lengthInMeters"])
    assert main.travel_time_s == pytest.approx(raw["summary"]["travelTimeInSeconds"])
    # At every progress point, distance and time are exactly TomTom's.
    for entry in raw["progress"]:
        assert main.distances_m[entry["pointIndex"]] == pytest.approx(entry["distanceInMeters"])
        assert main.times_s[entry["pointIndex"]] == pytest.approx(entry["travelTimeInSeconds"])


def small_route(**extra):
    points = [{"latitude": 30.0 + i / 100, "longitude": -100.0} for i in range(5)]
    route = {"summary": {"lengthInMeters": 4_450, "travelTimeInSeconds": 400}, "legs": [{"points": points}]}
    return {"routes": [{**route, **extra}]}


def test_instruction_timing_is_the_fallback(http):
    instructions = [
        {"pointIndex": 0, "routeOffsetInMeters": 0, "travelTimeInSeconds": 0},
        {"pointIndex": 2, "routeOffsetInMeters": 2_225, "travelTimeInSeconds": 300},
        {"pointIndex": 4, "routeOffsetInMeters": 4_450, "travelTimeInSeconds": 400},
    ]
    http.get(ROUTE, json=small_route(guidance={"instructions": instructions}))
    profile = tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=0, timeout_s=5)[0]
    assert profile.times_s[2] == pytest.approx(300)
    assert profile.time_at(1_112.5) == pytest.approx(150)


def test_multi_leg_routes_join_their_points_in_order(http):
    first = [{"latitude": 30.0, "longitude": -100.0}, {"latitude": 30.01, "longitude": -100.0}]
    second = [{"latitude": 30.01, "longitude": -100.0}, {"latitude": 30.02, "longitude": -100.0}]
    route = {
        "summary": {"lengthInMeters": 2_224, "travelTimeInSeconds": 200},
        "legs": [{"points": first}, {"points": second}],
        "progress": [
            {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
            {"pointIndex": 3, "distanceInMeters": 2_224, "travelTimeInSeconds": 200},
        ],
    }
    http.get(ROUTE, json={"routes": [route]})
    profile = tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=0, timeout_s=5)[0]
    assert len(profile.points) == 4
    assert profile.travel_time_s == 200


@pytest.mark.parametrize(
    ("status", "body", "error", "text"),
    [
        (
            400,
            {"detailedError": {"code": "NO_ROUTE_FOUND", "message": "No valid route found"}},
            NoRoute,
            "No truck route",
        ),
        (400, {"detailedError": {"code": "MAP_MATCHING_FAILURE", "message": "x"}}, NoRoute, "No truck route"),
        (
            401,
            {"detailedError": {"code": "Unauthorized", "message": "missing key"}},
            RoutingUnavailable,
            "TomTom key",
        ),
        (403, "<xml>Developer Over Qps</xml>", RoutingUnavailable, "TomTom key"),
        (429, {"error": {"description": "Too many requests"}}, RoutingUnavailable, "busy"),
        (500, {"detailedError": {"code": "INTERNAL", "message": "boom"}}, RoutingUnavailable, "error 500"),
        (200, "not json", RoutingUnavailable, "unreadable"),
        (200, {"routes": []}, NoRoute, "No truck route"),
        (200, {"routes": [{"summary": {}}]}, RoutingUnavailable, "unreadable"),
    ],
)
def test_route_errors(http, status, body, error, text):
    if isinstance(body, str):
        http.get(ROUTE, status=status, body=body)
    else:
        http.get(ROUTE, status=status, json=body)
    with pytest.raises(error) as caught:
        tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=2, timeout_s=15)
    assert text in caught.value.message


@pytest.mark.parametrize(
    "failure",
    [
        requests.ReadTimeout("read timed out"),
        # A stall partway through the body comes as a ConnectionError wrapping urllib3's timeout.
        requests.ConnectionError(ReadTimeoutError(None, None, "Read timed out.")),
    ],
)
def test_timeouts_are_reported_as_timeouts(http, failure):
    http.get(ROUTE, body=failure)
    with pytest.raises(RoutingTimeout, match="took too long"):
        tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=2, timeout_s=15)


def test_api_key_never_reaches_the_logs(http, caplog):
    secret_url = "https://api.tomtom.com/routing/1/calculateRoute/x/json?key=test-key"
    http.get(ROUTE, body=requests.ConnectionError(f"Max retries exceeded with url: {secret_url}"))
    with caplog.at_level(logging.WARNING, logger="trips"), pytest.raises(RoutingUnavailable):
        tomtom.calculate_routes(DALLAS, DENVER, DEPARTURE, alternatives=2, timeout_s=15)
    assert "test-key" not in caplog.text
    assert "key=***" in caplog.text


def test_error_bodies_in_any_shape_are_read():
    response = requests.Response()
    response.status_code = 400
    response._content = json.dumps(
        {"errorText": "bad language", "detailedError": {"code": "BadRequest"}}
    ).encode()
    assert tomtom._detail(response) == ("BadRequest", "bad language")
