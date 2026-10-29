"""The whole plan against fake TomTom and Open-Meteo services (real Dallas -> Denver routes)."""

from bisect import bisect_right
from datetime import UTC, datetime, timedelta
from itertools import chain, repeat

import pytest

from trips import planner
from trips.domain.grid import PLAN_LOCATION_BUDGET
from trips.domain.risk import RiskLevel
from trips.domain.times import epoch_seconds, eta_after, nearest_hour
from trips.errors import NoRoute, PlaceNotFound, SamePlace
from trips.planner import TripRequest, plan_trip

from .fakes import AMARILLO_BOX, DALLAS, SALINA_BOX, windy_in

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
DEPARTURE = datetime(2026, 10, 24, 15, 20, tzinfo=UTC)
STOPPED_EARLY = "Found 2 distinct truck routes; stopped looking for more to keep the plan quick."
FAILED = (
    "Found 2 distinct truck routes; the routing service didn't answer the search for more. Try again shortly."
)


def trip(interval_mi=25, load_lb=35_000, origin="Dallas, TX", destination="Denver, CO", departure=DEPARTURE):
    return TripRequest(origin, destination, departure, load_lb, interval_mi)


def plan(request=None, clock=None):
    if clock is None:
        return plan_trip(request or trip(), now=NOW)
    return plan_trip(request or trip(), now=NOW, clock=clock)


def all_levels(result):
    return {level for levels in result.heatmap_levels.values() for level in levels}


# Routes


def test_three_routes_with_a_via_route_when_tomtom_returns_two(services):
    result = plan()
    assert [route.route_id for route in result.routes] == ["A", "B", "C"]
    assert [route.route.via for route in result.routes] == [False, False, True]
    assert result.notices == []
    assert result.origin.name == "Dallas, TX"


def test_three_distinct_tomtom_routes_need_no_via_requests(services):
    services.main_routes["routes"].append(services.via_routes["routes"][0])
    result = plan()
    assert [route.route.via for route in result.routes] == [False, False, False]
    assert len(services.route_requests) == 1
    assert result.notices == []


def test_a_duplicate_tomtom_alternative_is_replaced_by_a_via_route(services):
    first, second = services.main_routes["routes"]
    services.main_routes["routes"] = [first, second, first]
    assert [route.route.via for route in plan().routes] == [False, False, True]


def test_slow_via_routes_are_rejected(services):
    slow = services.via_routes["routes"][0]
    slow["summary"]["travelTimeInSeconds"] *= 3
    for entry in slow["progress"]:
        entry["travelTimeInSeconds"] *= 3
    result = plan()
    assert len(result.routes) == 2
    assert result.notices == ["Only 2 distinct truck routes found for this trip."]


def test_via_routes_that_repeat_a_route_are_rejected(services):
    services.via_routes = {"routes": [services.main_routes["routes"][0]]}
    result = plan()
    assert len(result.routes) == 2
    assert result.notices == ["Only 2 distinct truck routes found for this trip."]


def test_no_route_through_the_via_points_is_a_definite_answer(services):
    services.via_error = (
        400,
        {"detailedError": {"code": "NO_ROUTE_FOUND", "message": "No valid route found"}},
    )
    result = plan()
    assert result.notices == ["Only 2 distinct truck routes found for this trip."]
    assert len(services.via_requests) == 4
    requests_so_far = len(services.route_requests)
    plan(trip(interval_mi=10))
    assert len(services.route_requests) == requests_so_far  # the answer was cached


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {"error": {"description": "Too many requests"}}),
        (503, {"detailedError": {"code": "SERVICE_UNAVAILABLE", "message": "down"}}),
        (403, {"detailedError": {"code": "Forbidden", "message": "Developer Over Qps"}}),
    ],
)
def test_a_routing_service_failure_is_not_taken_as_no_route(services, status, body):
    services.via_error = (status, body)
    result = plan()
    assert len(result.routes) == 2
    assert result.notices == [FAILED]
    assert len(services.via_requests) == 2  # no second pair after a failure
    services.via_error = None
    assert len(plan(trip(interval_mi=10)).routes) == 3  # searched again, not cached as "only 2"


# The time budget


def test_the_via_search_stops_when_its_time_is_up(services, monkeypatch):
    monkeypatch.setattr(planner, "VIA_SEARCH_MAX_S", 0.3)
    monkeypatch.setattr(planner, "MIN_VIA_ATTEMPT_S", 0.1)
    services.via_delay_s = 1.0
    result = plan()
    assert len(result.routes) == 2
    assert result.notices == [STOPPED_EARLY]


def test_a_slow_main_route_leaves_no_time_for_via_routes(services):
    clock = chain([0.0, 0.5], repeat(14.5)).__next__  # the main route answers 14 s into the plan
    result = plan(clock=clock)
    assert len(result.routes) == 2
    assert services.via_requests == []
    assert result.notices == [STOPPED_EARLY]


def test_an_interrupted_search_carries_on_in_the_next_plan(services, monkeypatch):
    monkeypatch.setattr(planner, "VIA_SEARCH_MAX_S", 0.3)
    monkeypatch.setattr(planner, "MIN_VIA_ATTEMPT_S", 0.1)
    services.via_delay_s = 1.0
    plan(trip(interval_mi=25))
    main_requests = len(services.route_requests) - len(services.via_requests)
    services.via_delay_s = 0.0
    result = plan(trip(interval_mi=10))
    assert len(result.routes) == 3
    assert len(services.route_requests) - len(services.via_requests) == main_requests  # not asked again


def test_when_alternatives_take_too_long_the_main_route_comes_alone(services):
    services.alternatives_time_out = True
    clock = chain([0.0, 0.5], repeat(16.5)).__next__  # the fallback answers 16 s into the plan
    result = plan(clock=clock)
    assert len(result.routes) == 1
    assert "maxAlternatives=0" in services.route_requests[-1]
    assert result.notices == ["Found 1 truck route; stopped looking for more to keep the plan quick."]


def test_changing_only_the_interval_reuses_routes_and_cached_weather(services):
    plan(trip(interval_mi=25))
    route_requests = len(services.route_requests)
    plan(trip(interval_mi=50))
    assert len(services.route_requests) == route_requests  # routes come from the cache
    assert len(services.weather_requests) == 1  # every 50-mile location was already fetched


# Checkpoints, ETAs and the weather


def test_checkpoint_etas_follow_tomtoms_progress_timing(services):
    # The expected ETA comes straight from TomTom's (distance, travel time) progress pairs, rounded
    # to the nearest minute.
    progress = services.main_routes["routes"][0]["progress"]
    meters = [entry["distanceInMeters"] for entry in progress]
    seconds = [entry["travelTimeInSeconds"] for entry in progress]
    route = plan().routes[0]
    for item in route.checkpoints:
        distance = item.checkpoint.distance_m
        i = min(bisect_right(meters, distance) - 1, len(meters) - 2)
        expected = seconds[i] + (seconds[i + 1] - seconds[i]) * (distance - meters[i]) / (
            meters[i + 1] - meters[i]
        )
        assert abs((item.eta - DEPARTURE).total_seconds() - expected) <= 30
        assert item.eta.second == 0 and item.eta.microsecond == 0
        assert item.forecast_hour == nearest_hour(item.eta)
    assert route.checkpoints[0].eta == DEPARTURE
    assert route.checkpoints[-1].eta == eta_after(DEPARTURE, seconds[-1])


def test_the_forecast_hour_follows_the_eta_shown(services):
    # Route A takes 42,699 s: 15:38 + 11:51:39 is 03:29:39, shown as 03:30, so it takes the 04:00 hour.
    route = plan(trip(departure=datetime(2026, 10, 24, 15, 38, tzinfo=UTC))).routes[0]
    destination = route.checkpoints[-1]
    assert destination.eta == datetime(2026, 10, 25, 3, 30, tzinfo=UTC)
    assert destination.forecast_hour == datetime(2026, 10, 25, 4, 0, tzinfo=UTC)


def test_the_forecast_window_ends_at_the_hour_of_the_last_eta_shown(services):
    # Route C takes 4 x 49,493 s: 15:30 + 54:59:32 is 22:29:32 two days later, shown as 22:30, which
    # needs the 23:00 forecast, past the 48-hour heatmap window.
    for routes in (services.main_routes, services.via_routes):
        for route in routes["routes"]:
            route["summary"]["travelTimeInSeconds"] *= 4
            for entry in route["progress"]:
                entry["travelTimeInSeconds"] *= 4
    destination = plan(trip(departure=datetime(2026, 10, 24, 15, 30, tzinfo=UTC))).routes[2].checkpoints[-1]
    assert destination.eta == datetime(2026, 10, 26, 22, 30, tzinfo=UTC)
    assert destination.forecast_hour == datetime(2026, 10, 26, 23, 0, tzinfo=UTC)
    assert destination.sample is not None


def test_checkpoint_spacing_follows_the_interval(services):
    result = plan(trip(interval_mi=50))
    miles = [round(item.checkpoint.distance_m / 1609.344, 3) for item in result.routes[0].checkpoints]
    assert miles[:3] == [0, 50, 100]
    assert miles[-1] == pytest.approx(result.routes[0].route.profile.length_m / 1609.344, abs=1e-3)


def test_a_default_plan_stays_within_the_location_budget(services):
    result = plan()
    assert result.weather_locations <= PLAN_LOCATION_BUDGET
    assert services.weather_locations == result.weather_locations
    assert len(services.weather_requests) == 1  # one batched request


def test_the_forecast_window_covers_arrivals_more_than_48_hours_out(services):
    for routes in (services.main_routes, services.via_routes):
        for route in routes["routes"]:
            route["summary"]["travelTimeInSeconds"] *= 5
            for entry in route["progress"]:
                entry["travelTimeInSeconds"] *= 5
    last = plan().routes[0].checkpoints[-1]
    assert last.eta - DEPARTURE > timedelta(hours=48)
    assert last.sample is not None


def test_hours_past_the_forecast_range_are_no_data(services):
    last_hour = datetime(2026, 11, 8, 23, 0, tzinfo=UTC)  # the last hour Open-Meteo forecasts from NOW
    result = plan(trip(departure=last_hour))
    route = result.routes[0]
    assert route.checkpoints[0].assessment.level is RiskLevel.LOW
    assert route.checkpoints[-1].sample is None
    assert route.checkpoints[-1].assessment.level is None
    assert result.recommendation.warnings[0].startswith("No forecast for")
    assert all(
        levels[0] is not None and set(levels[1:]) == {None} for levels in result.heatmap_levels.values()
    )


def test_missing_forecasts_are_no_data(services):
    services.weather = lambda lat, lon, epoch: {
        "wind_speed_10m": None, "wind_gusts_10m": None, "rain": 0.0, "showers": 0.0, "snowfall": 0.0
    }  # fmt: skip
    risk = plan().routes[0].risk
    assert risk.average_risk is None
    assert risk.no_data_miles == pytest.approx(risk.length_miles)


# The heatmap


def test_heatmap_covers_49_hours_from_the_departure_hour(services):
    result = plan()
    assert len(result.heatmap_hours) == 49
    assert result.heatmap_hours[0] == datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
    assert result.heatmap_hours[-1] == datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
    assert all(len(levels) == 49 for levels in result.heatmap_levels.values())


def test_hour_zero_is_the_hour_nearest_the_departure(services):
    late = plan(trip(departure=datetime(2026, 10, 24, 15, 40, tzinfo=UTC)))
    assert late.heatmap_hours[0] == datetime(2026, 10, 24, 16, 0, tzinfo=UTC)


def test_the_heatmap_is_the_same_at_every_interval(services):
    at_25 = plan(trip(interval_mi=25))
    at_10 = plan(trip(interval_mi=10))
    assert at_10.heatmap.grid.cells == at_25.heatmap.grid.cells
    assert at_10.heatmap_levels == at_25.heatmap_levels
    assert at_10.weather_locations > at_25.weather_locations


def test_the_heatmap_uses_the_entered_load(services):
    services.weather = windy_in(AMARILLO_BOX, mph=50)  # 45 up to 55 mph
    at_30k = all_levels(plan(trip(load_lb=30_000)))
    assert RiskLevel.SEVERE in at_30k and RiskLevel.NO_TRAVEL not in at_30k
    assert RiskLevel.NO_TRAVEL in all_levels(plan(trip(load_lb=30_001)))


def test_checkpoints_use_their_eta_while_the_heatmap_uses_the_slider_hour(services):
    # A storm over Salina only during the departure hour: the trucks get there hours later.
    departure_hour = epoch_seconds(datetime(2026, 10, 24, 15, 0, tzinfo=UTC))
    services.weather = windy_in(SALINA_BOX, mph=60, hours={departure_hour})
    result = plan()
    assert all(not route.risk.unsafe for route in result.routes)
    assert any(levels[0] is RiskLevel.NO_TRAVEL for levels in result.heatmap_levels.values())
    assert all(levels[1] is not RiskLevel.NO_TRAVEL for levels in result.heatmap_levels.values())


# Risk and the recommendation


def test_a_storm_on_one_route_makes_it_unsafe_and_another_is_recommended(services):
    services.weather = windy_in(AMARILLO_BOX, mph=50)  # 45 up to 55 mph with 35,000 lb: No Travel
    result = plan()
    assert result.routes[1].risk.unsafe
    assert all(not route.risk.unsafe for route in (result.routes[0], result.routes[2]))
    assert result.recommendation.route_id == "A"
    assert result.recommendation.warnings == ()


def test_the_load_rules_decide_between_severe_and_no_travel(services):
    services.weather = windy_in(AMARILLO_BOX, mph=50)
    light = plan(trip(load_lb=30_000)).routes[1].risk  # not above 30,000 lb: Severe
    assert light.miles(RiskLevel.SEVERE) > 0
    assert light.miles(RiskLevel.NO_TRAVEL) == 0


def test_when_the_fast_routes_are_unsafe_the_slower_safe_one_wins(services):
    services.weather = windy_in(SALINA_BOX, mph=60)  # No Travel on the main and via routes
    result = plan()
    assert result.recommendation.route_id == "B"
    assert result.recommendation.reason.startswith("Fewest No Travel miles: 0.0 mi vs")


def test_when_every_route_is_unsafe_the_least_bad_one_is_recommended_with_a_warning(services):
    services.weather = windy_in(((32.5, -97.2), (33.0, -96.5)), mph=60)  # at the shared origin
    result = plan()
    assert all(route.risk.unsafe for route in result.routes)
    assert "Every route has No Travel conditions" in result.recommendation.warnings[0]


# Places


def test_unknown_place(services):
    with pytest.raises(PlaceNotFound) as caught:
        plan(trip(destination="Nowhere, ZZ"))
    assert caught.value.field == "destination"


def test_same_place(services):
    services.places["downtown dallas"] = ("Dallas, TX", (DALLAS[0] + 0.001, DALLAS[1]))
    with pytest.raises(SamePlace):
        plan(trip(destination="Downtown Dallas"))


def test_no_route_names_the_places(services):
    services.main_routes = {"routes": []}
    with pytest.raises(NoRoute, match="between Dallas, TX and Denver, CO") as caught:
        plan()
    assert caught.value.field is None  # it's about the pair, not one of the two fields


def test_heatmap_causes_match_its_levels(services):
    services.weather = windy_in(AMARILLO_BOX, mph=50)

    result = plan()

    assert set(result.heatmap_causes) == set(result.heatmap_levels)
    for cell, causes in result.heatmap_causes.items():
        levels = result.heatmap_levels[cell]
        assert len(causes) == len(levels)
        # A cause is given exactly where there is a level to explain.
        assert [cause is None for cause in causes] == [level is None for level in levels]
    # The calm baseline is Low wind, and the storm is wind too.
    assert {cause for causes in result.heatmap_causes.values() for cause in causes} == {"wind"}
