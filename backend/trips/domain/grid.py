"""The heatmap: a grid of forecast points over a band around a trip's routes.

Open-Meteo's free tier counts every location in a request toward its limits (600 per minute
per IP). A plan at the default 25-mile interval should use at most ``PLAN_LOCATION_BUDGET``
locations, checkpoints included, so two plans can run back to back. The 25-mile checkpoints'
locations come first and the heatmap may only add what they leave. The heatmap is the same at
every interval, so changing the interval never changes it.

The grid is a fixed latitude/longitude lattice. A cell belongs to the heatmap when a route passes
through it or its centre is within ``BAND_M`` of a route. A cell that contains a 25-mile
checkpoint's forecast location reuses that forecast; any other cell is forecast at its centre,
which costs one more location. The cell size is the smallest of ``GRID_STEPS_DEG`` whose extra
locations fit the budget. If even the coarsest grid doesn't fit (on trips whose 25-mile checkpoints
alone need more than the budget), the coarsest grid is used anyway.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .geo import (
    METERS_PER_DEGREE,
    METERS_PER_MILE,
    LatLon,
    local_distance_m,
    meters_per_degree_lon,
    sample_along,
)

PLAN_LOCATION_BUDGET = 300  # half of Open-Meteo's free per-minute limit
GRID_STEPS_DEG = (0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0, 1.5, 2.0)
BAND_M = 10 * METERS_PER_MILE
ROUTE_SAMPLE_SPACING_M = 1_000.0  # routes are sampled once at this spacing for every grid size tried


@dataclass(frozen=True, order=True)
class GridCell:
    """A lattice cell: rows count latitude steps from the equator, columns longitude steps."""

    row: int
    col: int


def cell_for(point: LatLon, step_deg: float) -> GridCell:
    return GridCell(math.floor(point[0] / step_deg), math.floor(point[1] / step_deg))


# How close to a grid line, in cells, a point still counts as on it. This only absorbs float error
# (34.4 / 0.2 is 171.99999999999997): about 0.02 mm at 0.2 degrees.
ON_LINE = 1e-9


def cells_touching(point: LatLon, step_deg: float) -> set[GridCell]:
    """The cells whose edges contain a point: one, or two or four when it lies on grid lines.
    Locations are rounded to 0.01 degrees, so they often sit exactly on a line."""
    lat, lon = point[0] / step_deg, point[1] / step_deg
    rows = {math.floor(lat - ON_LINE), math.floor(lat + ON_LINE)}
    cols = {math.floor(lon - ON_LINE), math.floor(lon + ON_LINE)}
    return {GridCell(row, col) for row in rows for col in cols}


def cell_center(cell: GridCell, step_deg: float) -> LatLon:
    return (round((cell.row + 0.5) * step_deg, 6), round((cell.col + 0.5) * step_deg, 6))


class HeatmapGrid:
    """The cells of one trip's heatmap, sorted south to north, then west to east."""

    def __init__(self, step_deg: float, cells: Iterable[GridCell]) -> None:
        self.step_deg = step_deg
        self.cells: tuple[GridCell, ...] = tuple(sorted(set(cells)))
        if not self.cells:
            raise ValueError("a heatmap grid needs at least one cell")

    def __len__(self) -> int:
        return len(self.cells)

    def center(self, cell: GridCell) -> LatLon:
        return cell_center(cell, self.step_deg)

    def bounds(self, cell: GridCell) -> tuple[float, float, float, float]:
        """The cell's (south, west, north, east) edges in degrees."""
        step = self.step_deg
        return (
            round(cell.row * step, 6),
            round(cell.col * step, 6),
            round((cell.row + 1) * step, 6),
            round((cell.col + 1) * step, 6),
        )


Cell = tuple[int, int]  # (row, col): GridCell's plain form, used in the hot loop below


def _corner_cell(a: LatLon, b: LatLon, cell_a: Cell, cell_b: Cell, step_deg: float) -> Cell:
    """The cell a segment passes through when it moves diagonally from cell_a to a neighbouring
    cell_b: the one beyond whichever grid line the segment crosses first."""
    row_line = max(cell_a[0], cell_b[0]) * step_deg
    col_line = max(cell_a[1], cell_b[1]) * step_deg
    crosses_row_first = (row_line - a[0]) / (b[0] - a[0]) < (col_line - a[1]) / (b[1] - a[1])
    return (cell_b[0], cell_a[1]) if crosses_row_first else (cell_a[0], cell_b[1])


def _corridor(sampled_routes: Sequence[Sequence[LatLon]], step_deg: float, band_m: float) -> set[GridCell]:
    cell_m = step_deg * METERS_PER_DEGREE
    # Use samples about a quarter cell (and a quarter band) apart: consecutive samples are then never
    # more than one cell apart, and no centre's distance to the route is misjudged by much.
    target_m = (min(cell_m, band_m) if band_m > 0 else cell_m) / 4
    stride = max(1, int(target_m // ROUTE_SAMPLE_SPACING_M))
    row_reach = math.ceil(band_m / cell_m) + 1
    band_sq = band_m * band_m
    cells: set[Cell] = set()
    for samples in sampled_routes:
        points = list(samples[::stride])
        if points[-1] != samples[-1]:
            points.append(samples[-1])
        previous: tuple[LatLon, Cell] | None = None
        for lat, lon in points:
            home = (math.floor(lat / step_deg), math.floor(lon / step_deg))
            cells.add(home)
            if previous is not None:
                last_point, last = previous
                if abs(home[0] - last[0]) == 1 and abs(home[1] - last[1]) == 1:
                    cells.add(_corner_cell(last_point, (lat, lon), last, home, step_deg))
            previous = ((lat, lon), home)
            if band_m <= 0:
                continue
            # Flat-earth distance from this sample to nearby cell centres, written out for speed.
            lon_m = meters_per_degree_lon(lat)
            col_reach = math.ceil(band_m / (step_deg * lon_m)) + 1
            for row in range(home[0] - row_reach, home[0] + row_reach + 1):
                dy = ((row + 0.5) * step_deg - lat) * METERS_PER_DEGREE
                if dy * dy > band_sq:
                    continue
                for col in range(home[1] - col_reach, home[1] + col_reach + 1):
                    if (row, col) not in cells:
                        dx = ((col + 0.5) * step_deg - lon) * lon_m
                        if dx * dx + dy * dy <= band_sq:
                            cells.add((row, col))
    return {GridCell(row, col) for row, col in cells}


def corridor_cells(
    routes: Sequence[Sequence[LatLon]], step_deg: float, band_m: float = BAND_M
) -> set[GridCell]:
    """Cells a route passes through, plus cells whose centre is within band_m of a route."""
    return _corridor([sample_along(route, ROUTE_SAMPLE_SPACING_M) for route in routes], step_deg, band_m)


def forecast_points(grid: HeatmapGrid, known_locations: Iterable[LatLon]) -> dict[GridCell, LatLon]:
    """Where each cell's forecast comes from: the known location inside it (edges included) nearest
    its centre, or the centre when it has none. A location on the line between cells serves both."""
    members = set(grid.cells)
    nearest: dict[GridCell, tuple[float, LatLon]] = {}
    for location in sorted(set(known_locations)):
        for cell in cells_touching(location, grid.step_deg) & members:
            distance = local_distance_m(location, grid.center(cell))
            if cell not in nearest or distance < nearest[cell][0]:
                nearest[cell] = (distance, location)
    return {cell: nearest[cell][1] if cell in nearest else grid.center(cell) for cell in grid.cells}


@dataclass(frozen=True)
class Heatmap:
    grid: HeatmapGrid
    points: Mapping[GridCell, LatLon]  # where each cell's forecast comes from
    extra_locations: int  # forecast locations the heatmap adds beyond the known ones


def _heatmap(
    sampled_routes: Sequence[Sequence[LatLon]], step_deg: float, band_m: float, known: set[LatLon]
) -> Heatmap:
    grid = HeatmapGrid(step_deg, _corridor(sampled_routes, step_deg, band_m))
    points = forecast_points(grid, known)
    return Heatmap(grid, points, len(set(points.values()) - known))


def build_heatmap(
    routes: Sequence[Sequence[LatLon]],
    known_locations: Iterable[LatLon],
    budget: int = PLAN_LOCATION_BUDGET,
    band_m: float = BAND_M,
    steps_deg: Sequence[float] = GRID_STEPS_DEG,
) -> Heatmap:
    """The finest heatmap whose extra forecast locations fit in what the known locations (the
    25-mile checkpoints') leave of the budget.

    Steps are tried from coarse to fine, stopping at the first that adds too many locations, so the
    expensive fine grids of long trips are never built.
    """
    if not routes or not all(routes):
        raise ValueError("at least one non-empty route is needed")
    if not steps_deg:
        raise ValueError("at least one grid step is needed")
    known = set(known_locations)
    allowed = max(0, budget - len(known))
    sampled = [sample_along(route, ROUTE_SAMPLE_SPACING_M) for route in routes]
    steps = sorted(steps_deg, reverse=True)  # coarse to fine

    chosen = _heatmap(sampled, steps[0], band_m, known)
    if chosen.extra_locations > allowed:
        return chosen  # even the coarsest grid adds too many locations: use it anyway
    for step in steps[1:]:
        candidate = _heatmap(sampled, step, band_m, known)
        if candidate.extra_locations > allowed:
            break
        chosen = candidate
    return chosen
