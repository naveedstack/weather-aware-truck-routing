"""Route distinctness and via points for extra routes."""

from itertools import pairwise

import pytest

from trips.domain.alternatives import (
    VIA_OFFSET_MAX_M,
    VIA_OFFSET_MIN_M,
    RouteShape,
    are_distinct,
    distinct_indices,
    via_points,
)
from trips.domain.geo import (
    METERS_PER_DEGREE,
    METERS_PER_MILE,
    destination_point,
    haversine_m,
    initial_bearing_deg,
)
from trips.domain.profile import RouteProfile


def north_line(km: float, start=(35.0, -100.0), steps=200):
    return [(start[0] + km * 1000 * i / steps / METERS_PER_DEGREE, start[1]) for i in range(steps + 1)]


def with_detour(line, share: float, offset_km: float = 3.0):
    """The same line, with the middle `share` of its points moved east by offset_km."""
    count = len(line)
    first = int(count * (0.5 - share / 2))
    last = int(count * (0.5 + share / 2))
    return [
        destination_point(point, 90, offset_km * 1000) if first <= index < last else point
        for index, point in enumerate(line)
    ]


def test_identical_routes_are_not_distinct():
    line = RouteShape(north_line(100))
    assert line.share_apart_from(RouteShape(north_line(100))) == 0
    assert not are_distinct(line, RouteShape(north_line(100)))


def test_a_route_with_a_long_detour_is_distinct():
    line = north_line(100)
    detour = RouteShape(with_detour(line, 0.20))
    assert detour.share_apart_from(RouteShape(line)) == pytest.approx(0.20, abs=0.03)
    assert are_distinct(RouteShape(line), detour)


def test_a_small_detour_is_not_enough():
    line = north_line(100)
    assert not are_distinct(RouteShape(line), RouteShape(with_detour(line, 0.05)))


def test_routes_within_a_kilometre_are_the_same_road():
    line = north_line(100)
    nearby = [destination_point(point, 90, 600) for point in line]
    assert not are_distinct(RouteShape(line), RouteShape(nearby))


def test_distinct_indices_drops_repeats_in_order():
    line = north_line(100)
    shapes = [
        RouteShape(route) for route in (line, list(line), with_detour(line, 0.5), with_detour(line, 0.5))
    ]
    assert distinct_indices(shapes) == [0, 2]


def test_distinct_indices_stops_at_the_limit():
    line = north_line(100)
    shapes = [RouteShape(route) for route in (line, with_detour(line, 0.5), with_detour(line, 0.5, 6.0))]
    assert distinct_indices(shapes) == [0, 1, 2]
    assert distinct_indices(shapes, limit=2) == [0, 1]


def profile_for(line):
    distances = [0.0]
    for a, b in pairwise(line):
        distances.append(distances[-1] + haversine_m(a, b))
    return RouteProfile(line, distances, [d / 25 for d in distances])


def test_via_points_sit_beside_the_midpoint():
    line = north_line(160.9344)  # 100 miles due north
    middle = (35.0 + 80_467.2 / METERS_PER_DEGREE, -100.0)
    left, right, far_left, far_right = via_points(profile_for(line))

    # 10% of 100 miles is below the 15-mile minimum offset.
    assert haversine_m(middle, left) == pytest.approx(VIA_OFFSET_MIN_M, rel=1e-3)
    assert haversine_m(middle, far_right) == pytest.approx(2 * VIA_OFFSET_MIN_M, rel=1e-3)
    # Heading north: left is west, right is east, at the same latitude.
    assert left[1] < middle[1] < right[1]
    assert far_left[1] < left[1]
    assert right[0] == pytest.approx(middle[0], abs=0.01)


def test_via_offset_is_capped_for_long_routes():
    line = north_line(2_000 * METERS_PER_MILE / 1000)
    left = via_points(profile_for(line))[0]
    middle = (35.0 + 1_000 * METERS_PER_MILE / METERS_PER_DEGREE, -100.0)
    assert haversine_m(middle, left) == pytest.approx(VIA_OFFSET_MAX_M, rel=1e-3)


def test_a_bend_at_the_midpoint_does_not_turn_the_via_points():
    # About 400 miles east, with a 30 km jog north right at the middle of the route.
    west = [(35.0, -100.0 + 3.5 * i / 100) for i in range(101)]
    jog = destination_point(west[-1], 0, 30_000)
    east = [(jog[0], jog[1] + 3.5 * i / 100) for i in range(101)]
    profile = profile_for([*west, *east])
    middle = profile.position_at(profile.length_m / 2)
    left, right = via_points(profile)[:2]
    # Beside an eastbound route means north (left) and south (right), not along the jog.
    assert initial_bearing_deg(middle, left) == pytest.approx(360, abs=15) or initial_bearing_deg(
        middle, left
    ) == pytest.approx(0, abs=15)
    assert initial_bearing_deg(middle, right) == pytest.approx(180, abs=15)
