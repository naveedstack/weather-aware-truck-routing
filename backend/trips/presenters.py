"""The JSON returned by POST /api/plan/.

Numbers are rounded here, with the same helpers the ranking uses, so the UI shows exactly the
values that were compared. Risk levels are 0 (Low) to 4 (No Travel), or null for "No data".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .clients.tomtom import Place
from .domain.geo import METERS_PER_MILE
from .domain.ranking import round_half_up, shown_average, shown_miles, shown_minutes
from .domain.risk import RiskLevel, load_rule_text
from .domain.times import eta_after
from .domain.weather import WeatherSample
from .planner import CheckpointResult, RouteResult, TripPlan

NO_DATA_CODE = "-"  # stands for a missing level, or a missing cause, in the heatmap's strings
# What drove a cell's level, one character per hour, so the UI can say why a cell is coloured.
CAUSE_CODES = {"wind": "w", "rain": "r", "snow": "s"}


def _time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _level(level: RiskLevel | None) -> int | None:
    return None if level is None else int(level)


def _bbox(bounds: tuple[float, float, float, float]) -> list[float]:
    """[west, south, east, north]: the GeoJSON and MapLibre order, like the [lon, lat] lines."""
    south, west, north, east = bounds
    return [west, south, east, north]


def _place(place: Place, query: str) -> dict[str, Any]:
    return {"query": query, "name": place.name, "lat": place.position[0], "lon": place.position[1]}


def _checkpoint(result: CheckpointResult) -> dict[str, Any]:
    checkpoint, assessment = result.checkpoint, result.assessment
    weather = result.sample or WeatherSample(None, None, None, None)
    return {
        "mile": round_half_up(checkpoint.distance_m / METERS_PER_MILE, 1),
        "lat": round(checkpoint.position[0], 5),
        "lon": round(checkpoint.position[1], 5),
        "covers_mi": shown_miles(checkpoint.coverage_m / METERS_PER_MILE),
        "eta": _time(result.eta),
        "forecast_hour": _time(result.forecast_hour),
        "wind_mph": weather.wind_mph,
        "gust_mph": weather.gust_mph,
        "rain_in_per_hr": weather.rain_in_per_hr,
        "snow_in_per_hr": weather.snow_in_per_hr,
        "risk": _level(assessment.level),
        "wind_risk": _level(assessment.wind),
        "rain_risk": _level(assessment.rain),
        "snow_risk": _level(assessment.snow),
        "load_rule": load_rule_text(assessment),
    }


def _route(result: RouteResult, departure: datetime, recommended: bool) -> dict[str, Any]:
    profile, risk = result.route.profile, result.risk
    return {
        "id": result.route_id,
        "via": result.route.via,
        "recommended": recommended,
        "unsafe": risk.unsafe,
        "distance_mi": shown_miles(profile.length_m / METERS_PER_MILE),
        "travel_time_min": shown_minutes(profile.travel_time_s),
        "arrival": _time(eta_after(departure, profile.travel_time_s)),
        "average_risk": shown_average(risk.average_risk),
        "miles": {
            "no_travel": shown_miles(risk.miles(RiskLevel.NO_TRAVEL)),
            "severe": shown_miles(risk.miles(RiskLevel.SEVERE)),
            "high": shown_miles(risk.miles(RiskLevel.HIGH)),
            "moderate": shown_miles(risk.miles(RiskLevel.MODERATE)),
            "low": shown_miles(risk.miles(RiskLevel.LOW)),
            "no_data": shown_miles(risk.no_data_miles),
        },
        "line": [[round(lon, 5), round(lat, 5)] for lat, lon in result.route.line],  # GeoJSON order
        "checkpoints": [_checkpoint(item) for item in result.checkpoints],
    }


def plan_to_json(plan: TripPlan) -> dict[str, Any]:
    grid = plan.heatmap.grid
    return {
        "origin": _place(plan.origin, plan.request.origin),
        "destination": _place(plan.destination, plan.request.destination),
        "departure": _time(plan.request.departure),
        "load_lb": plan.request.load_lb,
        "interval_mi": plan.request.interval_mi,
        "routes": [
            _route(result, plan.request.departure, result.route_id == plan.recommendation.route_id)
            for result in plan.routes
        ],
        "recommendation": {
            "route_id": plan.recommendation.route_id,
            "reason": plan.recommendation.reason,
            "warnings": list(plan.recommendation.warnings),
        },
        "notices": plan.notices,
        "heatmap": {
            "cell_size_deg": grid.step_deg,
            "hours": [_time(hour) for hour in plan.heatmap_hours],
            "cells": [
                {
                    "bounds": _bbox(grid.bounds(cell)),
                    "levels": "".join(
                        NO_DATA_CODE if level is None else str(int(level))
                        for level in plan.heatmap_levels[cell]
                    ),
                    "causes": "".join(
                        CAUSE_CODES.get(cause or "", NO_DATA_CODE) for cause in plan.heatmap_causes[cell]
                    ),
                    # The cause's own value, comma separated, one slot per hour. Left empty below
                    # Moderate: the UI says nothing about a Low cell, so its reading is never needed
                    # and sending it would be the bulk of the heatmap.
                    "values": ",".join(
                        ""
                        if level is None or level < RiskLevel.MODERATE or reading is None
                        else f"{reading:g}"
                        for level, reading in zip(
                            plan.heatmap_levels[cell], plan.heatmap_readings[cell], strict=True
                        )
                    ),
                }
                for cell in grid.cells
            ],
        },
        "weather_locations": plan.weather_locations,
    }
