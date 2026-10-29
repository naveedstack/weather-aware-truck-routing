"""Distance and travel time along a route, taken from the routing API's own timing."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from .geo import LatLon, cumulative_distances_m, interpolate


@dataclass(frozen=True)
class TimingAnchor:
    """A polyline point where the routing API reports the cumulative travel time from the start.

    ``distance_m`` is the API's distance from the start to that point, when it gives one.
    """

    point_index: int
    travel_time_s: float
    distance_m: float | None = None


class RouteProfile:
    """Along-route distance and cumulative travel time at every polyline point."""

    def __init__(
        self,
        points: Sequence[LatLon],
        distances_m: Sequence[float],
        times_s: Sequence[float],
    ) -> None:
        if len(points) < 2 or not len(points) == len(distances_m) == len(times_s):
            raise ValueError("a route profile needs at least two points, each with a distance and a time")
        for values in (distances_m, times_s):
            if values[0] != 0 or any(later < earlier for earlier, later in pairwise(values)):
                raise ValueError("distances and times must start at 0 and never decrease")
        self.points = tuple(points)
        self.distances_m = tuple(distances_m)
        self.times_s = tuple(times_s)

    @property
    def length_m(self) -> float:
        return self.distances_m[-1]

    @property
    def travel_time_s(self) -> float:
        return self.times_s[-1]

    def _locate(self, distance_m: float) -> tuple[int, float]:
        """The segment holding a distance (clamped to the route) and the fraction along it."""
        distance = min(max(distance_m, 0.0), self.length_m)
        index = min(bisect_right(self.distances_m, distance) - 1, len(self.points) - 2)
        start, end = self.distances_m[index], self.distances_m[index + 1]
        fraction = (distance - start) / (end - start) if end > start else 0.0
        return index, fraction

    def position_at(self, distance_m: float) -> LatLon:
        """The point a given distance along the route."""
        index, fraction = self._locate(distance_m)
        return interpolate(self.points[index], self.points[index + 1], fraction)

    def time_at(self, distance_m: float) -> float:
        """Travel time in seconds from the start to a given distance along the route."""
        index, fraction = self._locate(distance_m)
        start, end = self.times_s[index], self.times_s[index + 1]
        return start + (end - start) * fraction


def build_profile(
    points: Sequence[LatLon],
    anchors: Sequence[TimingAnchor],
    length_m: float,
    travel_time_s: float,
) -> RouteProfile:
    """Spread the API's timing anchors over every polyline point.

    Between two anchors, distance and time grow in proportion to the straight-line distance
    between polyline points, which is how TomTom documents interpolating its progress data.
    ``length_m`` and ``travel_time_s`` are the route totals; they fill in the end anchor (and any
    anchor distance the API didn't give) when the anchors don't include them.
    """
    count = len(points)
    if count < 2:
        raise ValueError("a route needs at least two points")
    straight = cumulative_distances_m(points)
    scale = length_m / straight[-1] if straight[-1] > 0 else 0.0

    by_index = {anchor.point_index: anchor for anchor in anchors if 0 <= anchor.point_index < count}
    by_index[0] = TimingAnchor(0, 0.0, 0.0)  # the route starts at 0 m and 0 s, whatever the API says
    by_index.setdefault(count - 1, TimingAnchor(count - 1, travel_time_s, length_m))
    ordered = [by_index[index] for index in sorted(by_index)]

    def anchor_distance(anchor: TimingAnchor) -> float:
        if anchor.distance_m is not None:
            return anchor.distance_m
        return straight[anchor.point_index] * scale

    distances = [0.0] * count
    times = [0.0] * count
    for first, second in pairwise(ordered):
        start_m, end_m = anchor_distance(first), anchor_distance(second)
        base = straight[first.point_index]
        span = straight[second.point_index] - base
        for index in range(first.point_index, second.point_index + 1):
            if span > 0:
                fraction = (straight[index] - base) / span
            else:
                fraction = 1.0 if index == second.point_index else 0.0
            distances[index] = start_m + (end_m - start_m) * fraction
            times[index] = first.travel_time_s + (second.travel_time_s - first.travel_time_s) * fraction

    # Guard against inconsistent API data: distance and time never go backwards along a route.
    for index in range(1, count):
        distances[index] = max(distances[index], distances[index - 1])
        times[index] = max(times[index], times[index - 1])
    return RouteProfile(points, distances, times)
