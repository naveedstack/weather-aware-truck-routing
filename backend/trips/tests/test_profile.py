"""Travel time along a route from the routing API's timing anchors."""

import pytest

from trips.domain.geo import METERS_PER_DEGREE, METERS_PER_MILE
from trips.domain.profile import RouteProfile, TimingAnchor, build_profile


def meridian(*distances_m: float) -> list[tuple[float, float]]:
    """Points due north of (30, -100) at the given distances, so straight-line spacing is exact."""
    return [(30.0 + d / METERS_PER_DEGREE, -100.0) for d in distances_m]


def test_eta_follows_api_timing_not_an_average_speed():
    # 25 miles in 30 min, then the next 25 miles in 20 min.
    mile25, mile50 = 25 * METERS_PER_MILE, 50 * METERS_PER_MILE
    points = meridian(0, mile25 / 2, mile25, mile25 * 1.5, mile50)
    anchors = [TimingAnchor(0, 0, 0), TimingAnchor(2, 1_800, mile25), TimingAnchor(4, 3_000, mile50)]
    profile = build_profile(points, anchors, mile50, 3_000)

    assert profile.time_at(mile25) == pytest.approx(1_800)
    assert profile.time_at(37.5 * METERS_PER_MILE) == pytest.approx(2_400)
    assert profile.time_at(12.5 * METERS_PER_MILE) == pytest.approx(900)
    assert profile.time_at(0) == 0
    assert profile.time_at(mile50) == pytest.approx(3_000)


def test_distances_are_calibrated_to_the_api_length():
    # The straight-line polyline is 1% shorter than the road length the API reports.
    points = meridian(0, 50_000, 100_000)
    profile = build_profile(points, [], length_m=101_000, travel_time_s=4_000)
    assert profile.length_m == pytest.approx(101_000)
    assert profile.distances_m[1] == pytest.approx(50_500)
    assert profile.time_at(50_500) == pytest.approx(2_000)


def test_missing_end_anchors_come_from_route_totals():
    points = meridian(0, 1_000, 2_000)
    profile = build_profile(points, [TimingAnchor(1, 50)], length_m=2_000, travel_time_s=200)
    assert profile.times_s == pytest.approx((0, 50, 200))
    assert profile.distances_m == pytest.approx((0, 1_000, 2_000))


def test_anchor_without_distance_uses_scaled_straight_line_distance():
    points = meridian(0, 1_000, 2_000)
    profile = build_profile(points, [TimingAnchor(1, 60, None)], length_m=2_200, travel_time_s=120)
    assert profile.distances_m[1] == pytest.approx(1_100)


def test_duplicate_points_do_not_divide_by_zero():
    points = meridian(0, 1_000, 1_000, 2_000)
    anchors = [TimingAnchor(1, 100, 1_000), TimingAnchor(2, 100, 1_000)]
    profile = build_profile(points, anchors, length_m=2_000, travel_time_s=200)
    assert profile.time_at(1_000) == pytest.approx(100)
    assert profile.time_at(1_500) == pytest.approx(150)
    assert profile.position_at(1_000)[0] == pytest.approx(points[1][0])


def test_time_and_distance_never_go_backwards():
    points = meridian(0, 1_000, 2_000, 3_000)
    anchors = [TimingAnchor(1, 100, 1_000), TimingAnchor(2, 90, 1_900)]  # inconsistent API data
    profile = build_profile(points, anchors, length_m=3_000, travel_time_s=300)
    assert list(profile.times_s) == sorted(profile.times_s)
    assert list(profile.distances_m) == sorted(profile.distances_m)


def test_lookups_are_clamped_to_the_route():
    profile = RouteProfile(meridian(0, 1_000), [0, 1_000], [0, 60])
    assert profile.time_at(-5) == 0
    assert profile.time_at(5_000) == 60
    assert profile.position_at(5_000) == pytest.approx(profile.points[-1])


def test_position_is_interpolated_inside_a_segment():
    profile = RouteProfile(meridian(0, 40_000), [0, 40_000], [0, 1_000])
    lat, lon = profile.position_at(10_000)
    assert lat == pytest.approx(30.0 + 10_000 / METERS_PER_DEGREE)
    assert lon == -100.0


def test_profile_needs_two_points():
    with pytest.raises(ValueError):
        build_profile(meridian(0), [], 0, 0)
    with pytest.raises(ValueError):
        RouteProfile(meridian(0, 1), [0], [0, 1])


def test_the_origin_is_always_zero_metres_and_seconds():
    # An API anchor at point 0 with a non-zero distance must not move the origin.
    points = meridian(0, 1_000, 2_000)
    profile = build_profile(points, [TimingAnchor(0, 5.0, 10.0)], length_m=2_000, travel_time_s=100)
    assert profile.distances_m[0] == 0
    assert profile.times_s[0] == 0
    assert profile.position_at(0) == points[0]
    assert profile.time_at(0) == 0


def test_profile_rejects_distances_or_times_that_do_not_start_at_zero_or_go_backwards():
    points = meridian(0, 1_000, 2_000)
    with pytest.raises(ValueError):
        RouteProfile(points, [5, 1_000, 2_000], [0, 50, 100])
    with pytest.raises(ValueError):
        RouteProfile(points, [0, 1_000, 900], [0, 50, 100])
    with pytest.raises(ValueError):
        RouteProfile(points, [0, 1_000, 2_000], [0, 50, 40])


def test_anchors_outside_the_route_are_ignored():
    points = meridian(0, 1_000, 2_000)
    anchors = [TimingAnchor(-1, 999, 5), TimingAnchor(3, 999, 5)]
    profile = build_profile(points, anchors, length_m=2_000, travel_time_s=100)
    assert profile.times_s == pytest.approx((0, 50, 100))


def test_anchors_may_come_in_any_order():
    points = meridian(0, 1_000, 2_000)
    anchors = [TimingAnchor(2, 100, 2_000), TimingAnchor(1, 80, 1_000)]
    assert build_profile(points, anchors, 2_000, 100).times_s == pytest.approx((0, 80, 100))
