"""Checkpoints every N miles along a route, and the stretch of road each one stands for."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .geo import LatLon
from .profile import RouteProfile

# An interval point closer than this to the destination is merged into the destination.
MERGE_TOLERANCE_M = 1.0


@dataclass(frozen=True)
class Checkpoint:
    """A sampling point on a route.

    It stands for the road from ``coverage_start_m`` to ``coverage_end_m``: halfway to the
    previous and next checkpoints, or up to the origin/destination at the ends.
    """

    index: int
    distance_m: float
    position: LatLon
    elapsed_s: float  # travel time from the departure, per the routing API
    coverage_start_m: float
    coverage_end_m: float

    @property
    def coverage_m(self) -> float:
        return self.coverage_end_m - self.coverage_start_m


def checkpoint_distances(length_m: float, interval_m: float) -> list[float]:
    """The origin (0), every interval along the route, and the destination, in meters."""
    if interval_m <= 0:
        raise ValueError("interval_m must be positive")
    distances = [0.0]
    step = 1
    while step * interval_m < length_m - MERGE_TOLERANCE_M:
        distances.append(step * interval_m)
        step += 1
    if length_m > 0:
        distances.append(length_m)
    return distances


def coverage_bounds(distances: Sequence[float]) -> list[tuple[float, float]]:
    """For each checkpoint, the stretch from halfway to the previous one to halfway to the next."""
    last = len(distances) - 1
    bounds = []
    for index, distance in enumerate(distances):
        start = distances[0] if index == 0 else (distances[index - 1] + distance) / 2
        end = distances[last] if index == last else (distance + distances[index + 1]) / 2
        bounds.append((start, end))
    return bounds


def place_checkpoints(profile: RouteProfile, interval_m: float) -> list[Checkpoint]:
    """Checkpoints from the origin to the destination, with positions and travel times."""
    distances = checkpoint_distances(profile.length_m, interval_m)
    return [
        Checkpoint(
            index=index,
            distance_m=distance,
            position=profile.position_at(distance),
            elapsed_s=profile.time_at(distance),
            coverage_start_m=start,
            coverage_end_m=end,
        )
        for index, (distance, (start, end)) in enumerate(
            zip(distances, coverage_bounds(distances), strict=True)
        )
    ]
