"""Small geometry helpers on a spherical Earth.

Points are ``(latitude, longitude)`` tuples in degrees. GeoJSON and MapLibre use
``[longitude, latitude]``; TomTom and Open-Meteo put latitude first. Convert at the edges,
never in here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344
METERS_PER_DEGREE = math.pi * EARTH_RADIUS_M / 180  # along a meridian, about 111.2 km

LatLon = tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two points, in meters."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def meters_per_degree_lon(latitude: float) -> float:
    """Length of one degree of longitude at a latitude (kept above zero near the poles)."""
    return METERS_PER_DEGREE * max(math.cos(math.radians(latitude)), 0.01)


def local_distance_m(a: LatLon, b: LatLon) -> float:
    """Flat-earth distance. Much faster than haversine and accurate for points under ~100 km apart."""
    mean_lat = math.radians((a[0] + b[0]) / 2)
    dx = math.radians(b[1] - a[1]) * math.cos(mean_lat)
    dy = math.radians(b[0] - a[0])
    return EARTH_RADIUS_M * math.hypot(dx, dy)


def cumulative_distances_m(points: Sequence[LatLon]) -> list[float]:
    """Distance from the first point to every point along the polyline, in meters."""
    distances = [0.0]
    for a, b in pairwise(points):
        distances.append(distances[-1] + haversine_m(a, b))
    return distances


def interpolate(a: LatLon, b: LatLon, fraction: float) -> LatLon:
    """The point a given fraction of the way from a to b (linear in degrees; fine for short segments)."""
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)


def initial_bearing_deg(a: LatLon, b: LatLon) -> float:
    """Compass bearing from a to b in degrees, clockwise from north, in [0, 360)."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def destination_point(origin: LatLon, bearing_deg: float, distance_m: float) -> LatLon:
    """The point reached by travelling distance_m from origin along the given bearing."""
    lat1, lon1 = math.radians(origin[0]), math.radians(origin[1])
    bearing = math.radians(bearing_deg)
    angle = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(angle) + math.cos(lat1) * math.sin(angle) * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angle) * math.cos(lat1),
        math.cos(angle) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[LatLon]:
    """Douglas-Peucker simplification for drawing: keeps the first and last points and drops any
    point that lies within tolerance_m of the simplified line."""
    count = len(points)
    if count < 3:
        return list(points)
    # A flat projection around the middle latitude is accurate enough for a tolerance of meters.
    scale_x = METERS_PER_DEGREE * math.cos(math.radians(points[count // 2][0]))
    xs = [p[1] * scale_x for p in points]
    ys = [p[0] * METERS_PER_DEGREE for p in points]
    keep = [False] * count
    keep[0] = keep[-1] = True
    tolerance_sq = tolerance_m * tolerance_m
    stack = [(0, count - 1)]
    while stack:
        first, last = stack.pop()
        ax, ay = xs[first], ys[first]
        dx, dy = xs[last] - ax, ys[last] - ay
        length_sq = dx * dx + dy * dy
        farthest, farthest_sq = -1, tolerance_sq
        for index in range(first + 1, last):
            px, py = xs[index] - ax, ys[index] - ay
            if length_sq > 0:
                t = max(0.0, min(1.0, (px * dx + py * dy) / length_sq))
                px, py = px - t * dx, py - t * dy
            distance_sq = px * px + py * py
            if distance_sq > farthest_sq:
                farthest, farthest_sq = index, distance_sq
        if farthest >= 0:
            keep[farthest] = True
            stack.append((first, farthest))
            stack.append((farthest, last))
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def sample_along(points: Sequence[LatLon], spacing_m: float) -> list[LatLon]:
    """Points every spacing_m along the polyline, always including its first and last points."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if not points:
        return []
    samples = [points[0]]
    travelled = 0.0
    next_at = spacing_m
    for a, b in pairwise(points):
        segment = haversine_m(a, b)
        while segment > 0 and travelled + segment >= next_at:
            samples.append(interpolate(a, b, (next_at - travelled) / segment))
            next_at += spacing_m
        travelled += segment
    if samples[-1] != points[-1]:
        samples.append(points[-1])
    return samples
