"""Checkpoint placement and the miles each checkpoint covers."""

from itertools import pairwise

import pytest

from trips.domain.checkpoints import checkpoint_distances, coverage_bounds, place_checkpoints
from trips.domain.geo import METERS_PER_DEGREE, METERS_PER_MILE
from trips.domain.profile import RouteProfile

MILE = METERS_PER_MILE


def in_miles(values):
    return [value / MILE for value in values]


@pytest.mark.parametrize(
    ("length_mi", "interval_mi", "expected_mi"),
    [
        (100, 25, [0, 25, 50, 75, 100]),  # no duplicate at the end
        (107, 25, [0, 25, 50, 75, 100, 107]),  # last stretch is shorter
        (8, 25, [0, 8]),  # shorter than one interval: origin and destination only
        (25, 25, [0, 25]),
        (60, 50, [0, 50, 60]),
        (30, 10, [0, 10, 20, 30]),
    ],
)
def test_checkpoint_distances(length_mi, interval_mi, expected_mi):
    distances = checkpoint_distances(length_mi * MILE, interval_mi * MILE)
    assert in_miles(distances) == pytest.approx(expected_mi)


def test_interval_point_within_a_metre_of_the_destination_merges_into_it():
    distances = checkpoint_distances(25 * MILE + 0.5, 25 * MILE)
    assert distances == pytest.approx([0, 25 * MILE + 0.5])


@pytest.mark.parametrize(("interval_mi", "count"), [(10, 101), (25, 41), (50, 21)])
def test_checkpoint_counts_for_a_1000_mile_route(interval_mi, count):
    assert len(checkpoint_distances(1_000 * MILE, interval_mi * MILE)) == count


def test_interval_must_be_positive():
    with pytest.raises(ValueError):
        checkpoint_distances(1_000, 0)


@pytest.mark.parametrize(
    ("length_mi", "interval_mi", "expected_coverage_mi"),
    [
        (100, 25, [12.5, 25, 25, 25, 12.5]),
        (107, 25, [12.5, 25, 25, 25, 16, 3.5]),
        (8, 25, [4, 4]),
    ],
)
def test_coverage_is_halfway_to_each_neighbour(length_mi, interval_mi, expected_coverage_mi):
    distances = checkpoint_distances(length_mi * MILE, interval_mi * MILE)
    coverage = [(end - start) / MILE for start, end in coverage_bounds(distances)]
    assert coverage == pytest.approx(expected_coverage_mi)
    assert sum(coverage) == pytest.approx(length_mi)


def test_coverage_stretches_touch_without_gaps():
    bounds = coverage_bounds(checkpoint_distances(107 * MILE, 10 * MILE))
    assert bounds[0][0] == 0
    assert bounds[-1][1] == pytest.approx(107 * MILE)
    for (_, end), (start, _) in pairwise(bounds):
        assert end == pytest.approx(start)


def test_place_checkpoints_interpolates_positions_and_times():
    length = 60 * MILE
    north = (30.0 + length / METERS_PER_DEGREE, -100.0)
    profile = RouteProfile([(30.0, -100.0), north], [0, length], [0, 3_600])
    checkpoints = place_checkpoints(profile, 25 * MILE)

    assert [cp.index for cp in checkpoints] == [0, 1, 2, 3]
    assert in_miles(cp.distance_m for cp in checkpoints) == pytest.approx([0, 25, 50, 60])
    assert checkpoints[0].position == (30.0, -100.0)
    assert checkpoints[-1].position == pytest.approx(north)
    assert checkpoints[1].position[0] == pytest.approx(30.0 + 25 * MILE / METERS_PER_DEGREE)
    assert [cp.elapsed_s for cp in checkpoints] == pytest.approx([0, 1_500, 3_000, 3_600])
    assert sum(cp.coverage_m for cp in checkpoints) == pytest.approx(length)


def test_a_route_under_a_metre_keeps_its_origin_checkpoint():
    assert checkpoint_distances(0.5, 25 * MILE) == [0.0, 0.5]
    assert checkpoint_distances(0.0, 25 * MILE) == [0.0]


@pytest.mark.parametrize(("extra_m", "count"), [(1.0, 2), (1.5, 3)])
def test_merge_tolerance_is_one_metre(extra_m, count):
    assert len(checkpoint_distances(25 * MILE + extra_m, 25 * MILE)) == count


def test_checkpoint_times_follow_uneven_speeds_not_an_average():
    # 30 miles in 50 minutes, then 30 miles in 10 minutes.
    profile = RouteProfile(
        [(30.0, -100.0), (30.4, -100.0), (30.9, -100.0)], [0, 30 * MILE, 60 * MILE], [0, 3_000, 3_600]
    )
    assert [cp.elapsed_s for cp in place_checkpoints(profile, 25 * MILE)] == pytest.approx(
        [0, 2_500, 3_400, 3_600]
    )
