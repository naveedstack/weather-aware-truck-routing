from itertools import pairwise

import pytest

from trips.domain.geo import (
    METERS_PER_DEGREE,
    cumulative_distances_m,
    destination_point,
    haversine_m,
    initial_bearing_deg,
    local_distance_m,
    sample_along,
    simplify,
)


def test_one_degree_of_latitude():
    assert haversine_m((30.0, -100.0), (31.0, -100.0)) == pytest.approx(METERS_PER_DEGREE, rel=1e-9)
    assert METERS_PER_DEGREE == pytest.approx(111_195.08, abs=0.01)


def test_known_city_distance():
    dallas, denver = (32.7767, -96.7970), (39.7392, -104.9903)
    assert haversine_m(dallas, denver) / 1609.344 == pytest.approx(662.6, abs=1.0)


def test_local_distance_matches_haversine_nearby():
    a, b = (35.0, -101.0), (35.1, -100.9)
    assert local_distance_m(a, b) == pytest.approx(haversine_m(a, b), rel=1e-3)


def test_cumulative_distances():
    points = [(30.0, -100.0), (30.5, -100.0), (31.0, -100.0)]
    distances = cumulative_distances_m(points)
    assert distances[0] == 0
    assert distances[2] == pytest.approx(METERS_PER_DEGREE)


@pytest.mark.parametrize(
    ("bearing", "lat_sign", "lon_sign"), [(0, 1, 0), (90, 0, 1), (180, -1, 0), (270, 0, -1)]
)
def test_destination_point_directions(bearing, lat_sign, lon_sign):
    start = (35.0, -100.0)
    lat, lon = destination_point(start, bearing, 10_000)
    assert haversine_m(start, (lat, lon)) == pytest.approx(10_000, rel=1e-6)
    if lat_sign:
        assert (lat - start[0]) * lat_sign > 0
    if lon_sign:
        assert (lon - start[1]) * lon_sign > 0


def test_bearing_round_trip():
    start = (35.0, -100.0)
    end = destination_point(start, 63.0, 50_000)
    assert initial_bearing_deg(start, end) == pytest.approx(63.0, abs=1e-6)


def test_sample_along_spacing_and_ends():
    line = [(30.0, -100.0), (30.0 + 10_000 / METERS_PER_DEGREE, -100.0)]  # 10 km north
    samples = sample_along(line, 2_500)
    assert len(samples) == 5
    assert samples[0] == line[0]
    assert samples[-1] == line[-1]
    gaps = [haversine_m(a, b) for a, b in pairwise(samples)]
    assert gaps == pytest.approx([2_500] * 4, rel=1e-6)


def test_sample_along_keeps_last_point_when_spacing_does_not_divide():
    line = [(30.0, -100.0), (30.0 + 3_000 / METERS_PER_DEGREE, -100.0)]
    samples = sample_along(line, 2_000)
    assert len(samples) == 3
    assert samples[-1] == line[-1]


def test_sample_along_rejects_bad_spacing():
    with pytest.raises(ValueError):
        sample_along([(0.0, 0.0)], 0)


def test_simplify_drops_points_on_a_straight_line_and_keeps_corners():
    north = [(30.0 + i / 1000, -100.0) for i in range(11)]  # straight, 1.1 km
    east = [(30.01, -100.0 + i / 1000) for i in range(1, 11)]
    simplified = simplify([*north, *east], tolerance_m=5)
    assert simplified == [north[0], north[-1], east[-1]]


def test_simplify_keeps_bends_larger_than_the_tolerance():
    bend = [(30.0, -100.0), (30.005, -99.9995), (30.01, -100.0)]  # 48 m off the straight line
    assert simplify(bend, tolerance_m=30) == bend
    assert simplify(bend, tolerance_m=60) == [bend[0], bend[-1]]


def test_simplify_short_lines_are_unchanged():
    assert simplify([(30.0, -100.0), (30.1, -100.0)], tolerance_m=10) == [(30.0, -100.0), (30.1, -100.0)]
