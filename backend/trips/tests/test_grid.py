"""The heatmap grid: which cells cover a route's band, and fitting the location budget."""

import pytest

from trips.domain.geo import local_distance_m, sample_along
from trips.domain.grid import (
    BAND_M,
    GRID_STEPS_DEG,
    GridCell,
    HeatmapGrid,
    build_heatmap,
    cell_center,
    cell_for,
    cells_touching,
    corridor_cells,
    forecast_points,
)

# One degree due north, through the middle of a 0.1° column.
NORTH_LINE = [(30.0 + i / 10, -100.05) for i in range(11)]


def test_cell_maths():
    cell = cell_for((32.77, -96.79), 0.25)
    assert cell == GridCell(131, -388)
    assert cell_center(cell, 0.25) == (32.875, -96.875)
    assert HeatmapGrid(0.25, [cell]).bounds(cell) == (32.75, -97.0, 33.0, -96.75)


def test_band_covers_route_cells_and_nearby_centres_only():
    step = 0.1
    cells = corridor_cells([NORTH_LINE], step, BAND_M)

    # Every cell the route passes through is included.
    for point in sample_along(NORTH_LINE, 500):
        assert cell_for(point, step) in cells

    # Every included cell is crossed by the route or has its centre within the band.
    samples = sample_along(NORTH_LINE, 100)
    for cell in cells:
        nearest = min(local_distance_m(cell_center(cell, step), point) for point in samples)
        assert nearest <= BAND_M + 600

    # 0.1° of longitude is about 9.6 km here, so the band (16 km) reaches one column each side.
    assert {cell.col for cell in cells} == {-1002, -1001, -1000}


def test_no_band_means_only_crossed_cells():
    assert {cell.col for cell in corridor_cells([NORTH_LINE], 0.1, 0)} == {-1001}


def test_cell_clipped_at_a_corner_is_included():
    # This segment cuts 1.2 km across the corner of cell (0, 1); its centre is 37 km away.
    cells = corridor_cells([[(0.29, 0.40), (0.69, 0.60)]], 0.5, band_m=0)
    assert cells == {GridCell(0, 0), GridCell(0, 1), GridCell(1, 1)}


def test_overlapping_routes_share_cells():
    assert corridor_cells([NORTH_LINE, list(NORTH_LINE)], 0.1) == corridor_cells([NORTH_LINE], 0.1)


def test_cells_reuse_a_known_forecast_location_inside_them():
    grid = HeatmapGrid(0.5, [GridCell(0, 0), GridCell(0, 1)])
    known = [(0.10, 0.10), (0.24, 0.26), (5.0, 5.0)]  # the second is nearer cell (0, 0)'s centre
    assert forecast_points(grid, known) == {GridCell(0, 0): (0.24, 0.26), GridCell(0, 1): (0.25, 0.75)}


def test_a_location_on_a_grid_line_serves_both_cells():
    # 34.4 is the line between rows 171 and 172 at 0.2°, though 34.4 / 0.2 is 171.99999999999997.
    below, above = GridCell(171, -486), GridCell(172, -486)
    grid = HeatmapGrid(0.2, [below, above])
    assert forecast_points(grid, [(34.4, -97.14)]) == {below: (34.4, -97.14), above: (34.4, -97.14)}


@pytest.mark.parametrize(
    ("point", "cells"),
    [
        ((34.45, -97.15), {GridCell(172, -486)}),  # inside a cell
        ((34.4, -97.15), {GridCell(171, -486), GridCell(172, -486)}),  # on a row line
        ((34.45, -97.0), {GridCell(172, -486), GridCell(172, -485)}),  # on a column line
        ((34.4, -97.0), {GridCell(r, c) for r in (171, 172) for c in (-486, -485)}),  # on a corner
    ],
)
def test_cells_touching(point, cells):
    assert cells_touching(point, 0.2) == cells


def test_heatmap_uses_the_finest_grid_whose_extra_locations_fit():
    known = {(round(lat, 2), -100.05) for lat, _ in sample_along(NORTH_LINE, 40_000)}
    for budget in (len(known) + 5, len(known) + 40, len(known) + 200):
        allowed = budget - len(known)
        heatmap = build_heatmap([NORTH_LINE], known, budget=budget)
        assert heatmap.extra_locations <= allowed
        finer = [step for step in GRID_STEPS_DEG if step < heatmap.grid.step_deg]
        if finer:
            next_finer = build_heatmap([NORTH_LINE], known, budget=budget, steps_deg=[max(finer)])
            assert next_finer.extra_locations > allowed


def test_extra_locations_count_only_cells_without_a_known_location():
    known = {(30.05, -100.05)}
    heatmap = build_heatmap([NORTH_LINE], known, budget=10_000, steps_deg=[0.1])
    centres = [point for point in heatmap.points.values() if point not in known]
    assert heatmap.extra_locations == len(centres) == len(heatmap.grid) - 1


def test_over_budget_trips_still_get_the_finest_grid_that_adds_nothing():
    # 400 checkpoint locations along the route: over the budget, but every cell on the route can
    # reuse one of them, so a grid is fine as long as it adds no locations of its own.
    known = {(30.0 + i / 400, -100.05) for i in range(401)}
    heatmap = build_heatmap([NORTH_LINE], known, budget=300)
    assert heatmap.extra_locations == 0
    assert heatmap.grid.step_deg < max(GRID_STEPS_DEG)


def test_heatmap_falls_back_to_the_coarsest_grid():
    known = {(10.0 + i / 100, 10.0) for i in range(400)}  # over the budget and nowhere near the route
    heatmap = build_heatmap([NORTH_LINE], known, budget=300)
    assert heatmap.grid.step_deg == max(GRID_STEPS_DEG)
    assert heatmap.extra_locations == len(heatmap.grid)


def test_long_routes_get_coarser_cells():
    short = build_heatmap([NORTH_LINE[:3]], set(), budget=150)
    long = build_heatmap([[(30.0 + i / 10, -100.05) for i in range(101)]], set(), budget=150)  # 10 degrees
    assert long.grid.step_deg > short.grid.step_deg


def test_cells_are_sorted_and_unique():
    grid = HeatmapGrid(0.1, [GridCell(2, 1), GridCell(1, 5), GridCell(2, 1), GridCell(1, 2)])
    assert grid.cells == (GridCell(1, 2), GridCell(1, 5), GridCell(2, 1))


def test_invalid_inputs():
    with pytest.raises(ValueError):
        build_heatmap([], set())
    with pytest.raises(ValueError):
        build_heatmap([NORTH_LINE], set(), steps_deg=())
    with pytest.raises(ValueError):
        HeatmapGrid(0.1, [])
