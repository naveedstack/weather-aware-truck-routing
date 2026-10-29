"""Route risk totals, the ranking order and the recommendation."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .risk import RiskLevel


def round_half_up(value: float, decimals: int) -> float:
    """Round like people do (2.25 -> 2.3), unlike Python's round() (2.25 -> 2.2)."""
    quantum = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


# Display precision. The ranking compares these same values, so a tie on screen is a tie in the
# ranking. The API sends them as they are, so the UI never rounds differently.
def shown_miles(miles: float) -> float:
    """Miles to 0.1. Any positive distance shows as at least 0.1, so a short No Travel stretch
    can't hide behind 0.0 and tie with a route that has none."""
    return 0.0 if miles <= 0 else max(round_half_up(miles, 1), 0.1)


def shown_average(average: float | None) -> float | None:
    return None if average is None else round_half_up(average, 2)


def shown_minutes(seconds: float) -> int:
    return int(round_half_up(seconds / 60, 0))


def format_minutes(minutes: float) -> str:
    """'11 h 5 min', or '45 min' under an hour: the way the UI writes durations."""
    hours, rest = divmod(int(minutes), 60)
    return f"{hours} h {rest} min" if hours else f"{rest} min"


@dataclass(frozen=True)
class RouteRisk:
    """Risk totals for one route, built from its checkpoints."""

    route_id: str
    travel_time_s: float
    miles_by_level: Mapping[RiskLevel, float]
    no_data_miles: float
    average_risk: float | None  # None when no checkpoint has data

    def miles(self, level: RiskLevel) -> float:
        return self.miles_by_level[level]

    @property
    def length_miles(self) -> float:
        return sum(self.miles_by_level.values()) + self.no_data_miles

    @property
    def unsafe(self) -> bool:
        """Any No Travel miles make a route unsafe."""
        return self.miles(RiskLevel.NO_TRAVEL) > 0


def summarize_route(
    route_id: str,
    travel_time_s: float,
    stretches: Iterable[tuple[float, RiskLevel | None]],
) -> RouteRisk:
    """Totals from (miles a checkpoint covers, its level) pairs. A level of None is "No data".

    Average risk is weighted by miles (Low=0 ... No Travel=4) over the miles that have data;
    "No data" miles count as neither risky nor safe.
    """
    miles = dict.fromkeys(RiskLevel, 0.0)
    no_data = 0.0
    for covered, level in stretches:
        if level is None:
            no_data += covered
        else:
            miles[level] += covered
    known = sum(miles.values())
    average = sum(level * covered for level, covered in miles.items()) / known if known > 0 else None
    return RouteRisk(route_id, travel_time_s, miles, no_data, average)


@dataclass(frozen=True)
class _Criterion:
    name: str
    key: Callable[[RouteRisk], float]  # lower is better
    describe: Callable[[float], str]


def _describe_miles(miles: float) -> str:
    return f"{miles:,.1f} mi"  # "1,234.5 mi", like the UI


def _describe_average(average: float) -> str:
    return "No data" if average == math.inf else f"{average:.2f}"


def _miles_criterion(name: str, level: RiskLevel) -> _Criterion:
    return _Criterion(name, lambda route: shown_miles(route.miles(level)), _describe_miles)


def _average_key(route: RouteRisk) -> float:
    average = shown_average(route.average_risk)
    return math.inf if average is None else average


# The ranking order: the requirements' list, with No Travel miles first (see README "Assumptions").
CRITERIA = (
    _miles_criterion("Fewest No Travel miles", RiskLevel.NO_TRAVEL),
    _miles_criterion("Fewest Severe miles", RiskLevel.SEVERE),
    _miles_criterion("Fewest High miles", RiskLevel.HIGH),
    _Criterion("Lowest average risk", _average_key, _describe_average),
    _Criterion("Shortest travel time", lambda route: shown_minutes(route.travel_time_s), format_minutes),
)


def ranking_key(route: RouteRisk) -> tuple[float, ...]:
    return tuple(criterion.key(route) for criterion in CRITERIA)


def rank_routes(routes: Sequence[RouteRisk]) -> list[RouteRisk]:
    """Best route first. Routes that tie on everything keep the order they were found in."""
    return sorted(routes, key=ranking_key)


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    reason: str
    warnings: tuple[str, ...]


def _reason(best: RouteRisk, runner_up: RouteRisk | None) -> str:
    if runner_up is None:
        return "The only route found."
    for criterion in CRITERIA:
        mine, theirs = criterion.key(best), criterion.key(runner_up)
        if mine != theirs:
            return (
                f"{criterion.name}: {criterion.describe(mine)} vs "
                f"{criterion.describe(theirs)} on Route {runner_up.route_id}."
            )
    return f"Ties with Route {runner_up.route_id} on every measure; kept the order the routes were found in."


def recommend(routes: Sequence[RouteRisk]) -> Recommendation:
    """The best route by the ranking order, why it won, and any warnings to show with it."""
    if not routes:
        raise ValueError("no routes to recommend from")
    ranked = rank_routes(routes)
    best = ranked[0]
    warnings = []
    if all(route.unsafe for route in ranked):
        warnings.append(
            "Every route has No Travel conditions. "
            f"Route {best.route_id} is the least risky option, not a safe one."
        )
    if best.no_data_miles > 0:
        warnings.append(
            f"No forecast for {_describe_miles(shown_miles(best.no_data_miles))} of Route {best.route_id}, "
            "so its totals cover only the rest of the route."
        )
    return Recommendation(
        best.route_id, _reason(best, ranked[1] if len(ranked) > 1 else None), tuple(warnings)
    )
