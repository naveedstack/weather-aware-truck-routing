"""Mile totals, average risk, the ranking order and the recommendation text."""

import pytest

from trips.domain.ranking import (
    format_minutes,
    rank_routes,
    recommend,
    round_half_up,
    shown_average,
    shown_miles,
    shown_minutes,
    summarize_route,
)
from trips.domain.risk import RiskLevel

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)
HOUR = 3_600


def route(route_id, stretches, hours=10.0):
    return summarize_route(route_id, hours * HOUR, stretches)


def test_mile_totals_and_average():
    risk = route("A", [(12.5, L), (25, H), (25, S), (25, H), (12.5, L)])
    assert risk.miles(H) == 50
    assert risk.miles(S) == 25
    assert risk.miles(NT) == 0
    assert risk.average_risk == pytest.approx(1.75)
    assert risk.length_miles == 100
    assert not risk.unsafe


def test_no_data_miles_are_left_out_of_the_average():
    risk = route("A", [(12.5, L), (25, None), (25, S), (25, H), (12.5, L)])
    assert risk.no_data_miles == 25
    assert risk.average_risk == pytest.approx(125 / 75)
    assert risk.length_miles == 100


def test_average_is_none_without_any_data():
    assert route("A", [(4, None), (4, None)]).average_risk is None


def test_short_route_average():
    assert route("A", [(4, L), (4, S)]).average_risk == pytest.approx(1.5)


def test_extreme_averages():
    assert route("A", [(10, L)]).average_risk == 0
    assert route("A", [(10, NT)]).average_risk == 4


def test_any_no_travel_miles_make_a_route_unsafe():
    assert route("A", [(99.9, L), (0.01, NT)]).unsafe


def ids(routes):
    return [r.route_id for r in rank_routes(routes)]


def test_no_travel_miles_come_first():
    a = route("A", [(50, S), (50, L)])
    b = route("B", [(12.5, NT), (87.5, L)])
    assert ids([b, a]) == ["A", "B"]


def test_then_severe_then_high_then_average_then_time():
    assert ids([route("A", [(25, S), (75, L)]), route("B", [(12.5, S), (87.5, L)])]) == ["B", "A"]
    assert ids([route("A", [(37.5, H), (62.5, L)]), route("B", [(25, H), (75, L)])]) == ["B", "A"]
    assert ids([route("A", [(52, M), (48, L)]), route("B", [(40, M), (60, L)])]) == ["B", "A"]
    assert ids([route("A", [(100, L)], hours=10.0), route("B", [(100, L)], hours=9.99)]) == ["B", "A"]


def test_differences_hidden_by_display_rounding_are_ties():
    # 12.46 and 12.54 Severe miles both show as 12.5 (and both averages as 0.38), so travel time decides.
    a = route("A", [(12.46, S), (0.24, M), (87.30, L)], hours=9)
    b = route("B", [(12.54, S), (87.46, L)], hours=8)
    assert ids([a, b]) == ["B", "A"]
    # Average risk 0.404 vs 0.396 both show as 0.40.
    c = route("C", [(40.4, M), (59.6, L)], hours=9)
    d = route("D", [(39.6, M), (60.4, L)], hours=8)
    assert ids([d, c]) == ["D", "C"]


def test_full_ties_keep_the_given_order():
    a, b = route("A", [(100, L)]), route("B", [(100, L)])
    assert ids([a, b]) == ["A", "B"]
    assert ids([b, a]) == ["B", "A"]


def test_route_without_any_data_sorts_last_on_average():
    known = route("A", [(100, M)])
    unknown = route("B", [(100, None)])
    assert ids([unknown, known]) == ["A", "B"]


def test_recommendation_names_the_deciding_measure():
    a = route("A", [(25, S), (75, L)])
    b = route("B", [(100, L)])
    result = recommend([a, b])
    assert result.route_id == "B"
    assert result.reason == "Fewest Severe miles: 0.0 mi vs 25.0 mi on Route A."
    assert result.warnings == ()


def test_recommendation_on_travel_time():
    result = recommend([route("A", [(100, L)], hours=13.6), route("B", [(100, L)], hours=14.0)])
    assert result.reason == "Shortest travel time: 13 h 36 min vs 14 h 0 min on Route B."


@pytest.mark.parametrize(
    ("minutes", "text"), [(712, "11 h 52 min"), (605, "10 h 5 min"), (45, "45 min"), (0, "0 min")]
)
def test_durations_are_written_like_the_route_cards(minutes, text):
    assert format_minutes(minutes) == text


def test_long_distances_have_a_thousands_separator_like_the_route_cards():
    a = route("A", [(1500, L), (1234.5, None)], hours=40)
    b = route("B", [(1000, L), (2500.25, H)], hours=40)
    result = recommend([a, b])
    assert result.reason == "Fewest High miles: 0.0 mi vs 2,500.3 mi on Route B."
    assert result.warnings == (
        "No forecast for 1,234.5 mi of Route A, so its totals cover only the rest of the route.",
    )


def test_recommendation_on_average_with_missing_data():
    result = recommend([route("A", [(100, None)]), route("B", [(100, M)])])
    assert result.route_id == "B"
    assert result.reason == "Lowest average risk: 1.00 vs No data on Route A."


def test_full_tie_reason():
    result = recommend([route("A", [(100, L)]), route("B", [(100, L)])])
    assert result.route_id == "A"
    assert result.reason == "Ties with Route B on every measure; kept the order the routes were found in."


def test_single_route():
    result = recommend([route("A", [(100, L)])])
    assert result.route_id == "A"
    assert result.reason == "The only route found."


def test_all_routes_unsafe_still_recommends_the_least_bad_one():
    routes = [
        route("A", [(25, NT), (75, L)]),
        route("B", [(12.5, NT), (87.5, L)]),
        route("C", [(50, NT), (50, L)]),
    ]
    result = recommend(routes)
    assert result.route_id == "B"
    assert result.warnings[0] == (
        "Every route has No Travel conditions. Route B is the least risky option, not a safe one."
    )


def test_one_unsafe_route_is_not_recommended_and_no_global_warning():
    result = recommend([route("A", [(5, NT), (95, L)]), route("B", [(100, H)])])
    assert result.route_id == "B"
    assert result.warnings == ()


def test_warning_when_the_recommended_route_lacks_data():
    result = recommend([route("A", [(80, L), (20, None)])])
    assert result.warnings == (
        "No forecast for 20.0 mi of Route A, so its totals cover only the rest of the route.",
    )


def test_recommend_needs_routes():
    with pytest.raises(ValueError):
        recommend([])


@pytest.mark.parametrize(
    ("value", "decimals", "expected"), [(2.25, 1, 2.3), (12.45, 1, 12.5), (0.125, 2, 0.13), (59.5, 0, 60)]
)
def test_round_half_up(value, decimals, expected):
    assert round_half_up(value, decimals) == expected


def test_a_tiny_no_travel_stretch_still_loses_to_a_safe_route():
    # A destination checkpoint can cover only a few yards; its No Travel must still count.
    tail = route("A", [(99.96, L), (0.04, NT)])
    safe = route("B", [(100, H)])
    result = recommend([tail, safe])
    assert tail.unsafe
    assert result.route_id == "B"
    assert result.reason == "Fewest No Travel miles: 0.0 mi vs 0.1 mi on Route A."


def test_a_tiny_no_data_stretch_is_reported_as_at_least_a_tenth_of_a_mile():
    result = recommend([route("A", [(5, L), (0.03, None)])])
    assert result.warnings == (
        "No forecast for 0.1 mi of Route A, so its totals cover only the rest of the route.",
    )


@pytest.mark.parametrize(
    ("miles", "shown"),
    [
        (0, 0.0),
        (-1, 0.0),
        (0.0001, 0.1),
        (0.04, 0.1),
        (0.05, 0.1),
        (0.15, 0.2),
        (12.45, 12.5),
        (10.000000000000002, 10.0),
    ],
)
def test_shown_miles(miles, shown):
    assert shown_miles(miles) == shown


def test_shown_average_and_minutes():
    assert shown_average(None) is None
    assert shown_average(0.375) == 0.38
    assert shown_minutes(3629) == 60
    assert shown_minutes(3631) == 61
