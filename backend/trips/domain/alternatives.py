"""Telling routes apart, and choosing via points when the routing API returns too few routes."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from .geo import (
    METERS_PER_DEGREE,
    METERS_PER_MILE,
    LatLon,
    destination_point,
    initial_bearing_deg,
    local_distance_m,
    meters_per_degree_lon,
    sample_along,
)
from .profile import RouteProfile

# Two routes are distinct when at least DISTINCT_SHARE of one route's length lies more than
# SEPARATION_M from the other.
DISTINCT_SHARE = 0.10
SEPARATION_M = 1_000.0
SAMPLE_SPACING_M = 500.0

# Extra routes go through a TomTom circle waypoint beside the main route's midpoint.
VIA_RADIUS_M = 15_000
VIA_OFFSET_SHARE = 0.10  # offset = 10% of the route length, kept within the bounds below
VIA_OFFSET_MIN_M = 15 * METERS_PER_MILE
VIA_OFFSET_MAX_M = 100 * METERS_PER_MILE
# "Beside" is judged against the route's direction over its middle half, so a local bend or
# interchange at the midpoint doesn't put the via points ahead of or behind the route.
HEADING_WINDOW_SHARE = 0.25
MAX_DETOUR_RATIO = 1.5  # a via route may take at most 1.5x the main route's travel time


class RouteShape:
    """A route's evenly spaced sample points, with a spatial index over them. Built once per
    route, then compared with other routes as often as needed."""

    def __init__(self, points: Sequence[LatLon]) -> None:
        self.samples = sample_along(points, SAMPLE_SPACING_M)
        self._cell_deg = SEPARATION_M / METERS_PER_DEGREE
        self._buckets: dict[tuple[int, int], list[LatLon]] = defaultdict(list)
        for point in self.samples:
            self._buckets[self._bucket(point)].append(point)

    def _bucket(self, point: LatLon) -> tuple[int, int]:
        return (math.floor(point[0] / self._cell_deg), math.floor(point[1] / self._cell_deg))

    def is_near(self, point: LatLon) -> bool:
        """Whether any sample of this route is within SEPARATION_M of the point."""
        row, col = self._bucket(point)
        # A degree of longitude is shorter than a degree of latitude, so look further east and west.
        col_reach = math.ceil(METERS_PER_DEGREE / meters_per_degree_lon(point[0]))
        for d_row in (-1, 0, 1):
            for d_col in range(-col_reach, col_reach + 1):
                for sample in self._buckets.get((row + d_row, col + d_col), ()):
                    if local_distance_m(point, sample) <= SEPARATION_M:
                        return True
        return False

    def share_apart_from(self, other: RouteShape) -> float:
        """The share of this route's length that lies more than SEPARATION_M from the other route."""
        apart = sum(1 for point in self.samples if not other.is_near(point))
        return apart / len(self.samples)


def are_distinct(a: RouteShape, b: RouteShape) -> bool:
    return a.share_apart_from(b) >= DISTINCT_SHARE or b.share_apart_from(a) >= DISTINCT_SHARE


def distinct_indices(shapes: Sequence[RouteShape], limit: int | None = None) -> list[int]:
    """Indices of the routes to keep, in order: each must be distinct from every route kept
    before it. Stops once ``limit`` routes are kept."""
    kept: list[int] = []
    for index, shape in enumerate(shapes):
        if limit is not None and len(kept) >= limit:
            break
        if all(are_distinct(shape, shapes[other]) for other in kept):
            kept.append(index)
    return kept


def via_points(main: RouteProfile) -> list[LatLon]:
    """Points beside the main route's midpoint to route through: left, right, then twice as far."""
    middle = main.length_m / 2
    here = main.position_at(middle)
    span = HEADING_WINDOW_SHARE * main.length_m
    heading = initial_bearing_deg(main.position_at(middle - span), main.position_at(middle + span))
    offset = min(max(VIA_OFFSET_SHARE * main.length_m, VIA_OFFSET_MIN_M), VIA_OFFSET_MAX_M)
    return [
        destination_point(here, heading - 90, offset),
        destination_point(here, heading + 90, offset),
        destination_point(here, heading - 90, 2 * offset),
        destination_point(here, heading + 90, 2 * offset),
    ]
