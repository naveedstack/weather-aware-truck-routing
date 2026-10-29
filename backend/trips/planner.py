"""Plans a trip: routes, checkpoints, weather, risk levels, the recommendation and the heatmap."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from django.core.cache import cache

from .clients import openmeteo, tomtom
from .domain.alternatives import MAX_DETOUR_RATIO, RouteShape, are_distinct, distinct_indices, via_points
from .domain.checkpoints import Checkpoint, place_checkpoints
from .domain.geo import METERS_PER_MILE, LatLon, haversine_m, simplify
from .domain.grid import GridCell, Heatmap, build_heatmap
from .domain.profile import RouteProfile
from .domain.ranking import Recommendation, RouteRisk, recommend, summarize_route
from .domain.risk import Assessment, RiskLevel, leading_condition
from .domain.times import HOUR, epoch_seconds, eta_after, nearest_hour
from .domain.weather import Forecast, WeatherSample, assess_sample, leading_reading, location_key
from .errors import NoRoute, PlanError, RoutingTimeout, SamePlace

logger = logging.getLogger(__name__)

ROUTE_COUNT = 3
DEFAULT_INTERVAL_MI = 25  # the heatmap and the location budget are sized for this interval
HEATMAP_HOURS = 48
MIN_TRIP_M = 0.5 * METERS_PER_MILE  # closer than this, origin and destination are the same place

# Time budget: a plan should finish in about PLAN_TIME_BUDGET_S. The extra-route search gets what
# is left after the main route, minus WEATHER_RESERVE_S for the weather fetch and the rest.
PLAN_TIME_BUDGET_S = 20.0
WEATHER_RESERVE_S = 5.0
VIA_SEARCH_MAX_S = 8.0
MIN_VIA_ATTEMPT_S = 1.5  # don't start a via request with less time than this left
# TomTom's request with alternatives can take 15 s or more on very long trips (about 18 s for
# Anchorage -> Miami), while the main route alone takes a few seconds. If the alternatives don't
# arrive in time, the plan asks for the main route alone and goes on with fewer routes.
ALTERNATIVES_TIMEOUT_S = 15.0
MAIN_ROUTE_TIMEOUT_S = 8.0

LINE_TOLERANCE_M = 15.0  # route lines sent to the map are simplified to within this distance
ROUTE_CACHE_S = 15 * 60


@dataclass(frozen=True)
class TripRequest:
    origin: str
    destination: str
    departure: datetime  # time zone aware
    load_lb: float
    interval_mi: int


@dataclass(frozen=True)
class FoundRoute:
    profile: RouteProfile
    via: bool  # True for an extra route through a via point
    line: tuple[LatLon, ...] = ()  # simplified for drawing, once the route search is over


@dataclass(frozen=True)
class CheckpointResult:
    checkpoint: Checkpoint
    eta: datetime
    forecast_hour: datetime
    sample: WeatherSample | None
    assessment: Assessment


@dataclass(frozen=True)
class RouteResult:
    route_id: str
    route: FoundRoute
    checkpoints: list[CheckpointResult]
    risk: RouteRisk


@dataclass(frozen=True)
class TripPlan:
    request: TripRequest
    origin: tomtom.Place
    destination: tomtom.Place
    routes: list[RouteResult]
    recommendation: Recommendation
    heatmap: Heatmap
    heatmap_hours: list[datetime]
    heatmap_levels: dict[GridCell, list[RiskLevel | None]]
    heatmap_causes: dict[GridCell, list[str | None]]  # the condition behind each level, for the UI
    heatmap_readings: dict[GridCell, list[float | None]]  # that condition's value, in its own unit
    notices: list[str]
    weather_locations: int


def plan_trip(
    request: TripRequest,
    *,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> TripPlan:
    started = clock()
    deadline = started + PLAN_TIME_BUDGET_S
    departure = request.departure.astimezone(UTC)

    origin, destination = _geocode(request)
    if haversine_m(origin.position, destination.position) < MIN_TRIP_M:
        raise SamePlace("Origin and destination are the same place.", field="destination")
    geocoded = clock()
    search = _find_routes(origin, destination, departure, deadline, clock)
    routes = search.routes
    routed = clock()

    # Checkpoints at the chosen interval. The heatmap is sized for the default interval's locations,
    # so it is the same whichever interval is chosen.
    checkpoints = [
        place_checkpoints(route.profile, request.interval_mi * METERS_PER_MILE) for route in routes
    ]
    default_locations = {
        location_key(checkpoint.position)
        for route in routes
        for checkpoint in place_checkpoints(route.profile, DEFAULT_INTERVAL_MI * METERS_PER_MILE)
    }
    heatmap = build_heatmap([route.profile.points for route in routes], default_locations)
    gridded = clock()

    # One weather fetch for everything: from the departure's forecast hour to the later of
    # +48 hours and the last arrival.
    first_hour = nearest_hour(departure)
    last_arrival = eta_after(departure, max(route.profile.travel_time_s for route in routes))
    last_hour = max(first_hour + HEATMAP_HOURS * HOUR, nearest_hour(last_arrival))
    locations = {location_key(cp.position) for route_checkpoints in checkpoints for cp in route_checkpoints}
    locations |= set(heatmap.points.values())
    forecasts = openmeteo.fetch_forecasts(locations, first_hour, last_hour, now=now)
    fetched = clock()

    results = [
        _assess_route(chr(ord("A") + index), route, route_checkpoints, forecasts, departure, request.load_lb)
        for index, (route, route_checkpoints) in enumerate(zip(routes, checkpoints, strict=True))
    ]
    hours = [first_hour + step * HOUR for step in range(HEATMAP_HOURS + 1)]
    assessed_cells = {
        cell: [
            (sample, assess_sample(sample, request.load_lb))
            for sample in (forecasts[point].get(epoch_seconds(hour)) for hour in hours)
        ]
        for cell, point in heatmap.points.items()
    }
    levels = {cell: [item.level for _, item in items] for cell, items in assessed_cells.items()}
    causes = {cell: [leading_condition(item) for _, item in items] for cell, items in assessed_cells.items()}
    readings = {
        cell: [leading_reading(sample, item) for sample, item in items]
        for cell, items in assessed_cells.items()
    }
    logger.info(
        "Plan: %d routes, %d weather locations, %d heatmap cells of %.3g°. Seconds: geocode %.1f, "
        "routes %.1f, grid %.1f, weather %.1f, total %.1f",
        len(results),
        len(locations),
        len(heatmap.grid),
        heatmap.grid.step_deg,
        geocoded - started,
        routed - geocoded,
        gridded - routed,
        fetched - gridded,
        clock() - started,
    )
    return TripPlan(
        request=request,
        origin=origin,
        destination=destination,
        routes=results,
        recommendation=recommend([result.risk for result in results]),
        heatmap=heatmap,
        heatmap_hours=hours,
        heatmap_levels=levels,
        heatmap_causes=causes,
        heatmap_readings=readings,
        notices=search.notices(),
        weather_locations=len(locations),
    )


def _assess_route(
    route_id: str,
    route: FoundRoute,
    checkpoints: list[Checkpoint],
    forecasts: dict[LatLon, Forecast],
    departure: datetime,
    load_lb: float,
) -> RouteResult:
    """Each checkpoint's weather at the forecast hour nearest its ETA, and the route's totals."""
    assessed = []
    for checkpoint in checkpoints:
        eta = eta_after(departure, checkpoint.elapsed_s)
        hour = nearest_hour(eta)
        sample = forecasts[location_key(checkpoint.position)].get(epoch_seconds(hour))
        assessed.append(CheckpointResult(checkpoint, eta, hour, sample, assess_sample(sample, load_lb)))
    risk = summarize_route(
        route_id,
        route.profile.travel_time_s,
        [(item.checkpoint.coverage_m / METERS_PER_MILE, item.assessment.level) for item in assessed],
    )
    return RouteResult(route_id, route, assessed, risk)


def _geocode(request: TripRequest) -> tuple[tomtom.Place, tomtom.Place]:
    """Both places, looked up at the same time."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        origin = pool.submit(tomtom.geocode, request.origin, "origin")
        destination = pool.submit(tomtom.geocode, request.destination, "destination")
        return origin.result(), destination.result()


@dataclass
class RouteSearch:
    """The routes found for one trip so far. It is cached, so a later plan for the same trip (say, at
    another interval) reuses the routes, and carries on searching if this one was cut short."""

    routes: list[FoundRoute]
    untried: list[LatLon]  # via points with no definite answer yet
    outcome: str = "complete"  # or "out_of_time", or "failed" (the routing service didn't answer)

    def notices(self) -> list[str]:
        count = len(self.routes)
        if count >= ROUTE_COUNT:
            return []
        found = f"{count} distinct truck routes" if count > 1 else "1 truck route"
        if self.outcome == "complete":
            return [f"Only {found} found for this trip."]
        if self.outcome == "failed":
            return [
                f"Found {found}; the routing service didn't answer the search for more. Try again shortly."
            ]
        return [f"Found {found}; stopped looking for more to keep the plan quick."]


def _find_routes(
    origin: tomtom.Place,
    destination: tomtom.Place,
    departure: datetime,
    deadline: float,
    clock: Callable[[], float],
) -> RouteSearch:
    """Up to three distinct routes: TomTom's own, then extra ones through via points if needed."""
    key = (
        "routes:"
        + hashlib.sha256(repr((origin.position, destination.position, departure)).encode()).hexdigest()
    )
    search: RouteSearch | None = cache.get(key)
    if search is not None and search.outcome == "complete":
        return search
    if search is None:
        search = _first_routes(origin, destination, departure)
    if len(search.routes) < ROUTE_COUNT and search.untried:
        search.outcome = _search_via_routes(search, origin, destination, departure, deadline, clock)
    else:
        search.outcome = "complete"
    # Lines for the map are simplified once the search is over, so it doesn't eat into the search time.
    search.routes = [
        route if route.line else replace(route, line=tuple(simplify(route.profile.points, LINE_TOLERANCE_M)))
        for route in search.routes
    ]
    cache.set(key, search, ROUTE_CACHE_S)
    return search


def _first_routes(origin: tomtom.Place, destination: tomtom.Place, departure: datetime) -> RouteSearch:
    """TomTom's main route and its alternatives, keeping the distinct ones."""
    try:
        try:
            profiles = tomtom.calculate_routes(
                origin.position,
                destination.position,
                departure,
                alternatives=ROUTE_COUNT - 1,
                timeout_s=ALTERNATIVES_TIMEOUT_S,
            )
        except RoutingTimeout:
            # On very long trips TomTom takes much longer to find alternatives than the main route.
            logger.warning(
                "TomTom alternatives took over %.0f s; asking for the main route alone",
                ALTERNATIVES_TIMEOUT_S,
            )
            profiles = tomtom.calculate_routes(
                origin.position,
                destination.position,
                departure,
                alternatives=0,
                timeout_s=MAIN_ROUTE_TIMEOUT_S,
            )
    except NoRoute:
        raise NoRoute(f"No truck route found between {origin.name} and {destination.name}.") from None
    kept = distinct_indices([RouteShape(profile.points) for profile in profiles], limit=ROUTE_COUNT)
    routes = [FoundRoute(profiles[index], via=False) for index in kept]
    untried = via_points(routes[0].profile) if len(routes) < ROUTE_COUNT else []
    return RouteSearch(routes, untried)


def _search_via_routes(
    search: RouteSearch,
    origin: tomtom.Place,
    destination: tomtom.Place,
    departure: datetime,
    deadline: float,
    clock: Callable[[], float],
) -> str:
    """Add routes through via points beside the main route until there are three, within the time
    budget. Two candidates are tried at a time (left and right, then twice as far). A candidate
    leaves `search.untried` once TomTom gives a definite answer for it. Returns the outcome."""
    main = search.routes[0].profile
    shapes = [RouteShape(route.profile.points) for route in search.routes]
    search_deadline = min(deadline - WEATHER_RESERVE_S, clock() + VIA_SEARCH_MAX_S)
    while search.untried and len(search.routes) < ROUTE_COUNT:
        remaining = search_deadline - clock()
        if remaining < MIN_VIA_ATTEMPT_S:
            return "out_of_time"
        pair = search.untried[:2]
        pool = ThreadPoolExecutor(max_workers=len(pair))
        futures = [
            pool.submit(
                tomtom.calculate_routes,
                origin.position,
                destination.position,
                departure,
                alternatives=0,
                timeout_s=remaining,
                via=via,
            )
            for via in pair
        ]
        done, pending = wait(futures, timeout=remaining)
        pool.shutdown(wait=False, cancel_futures=True)  # never wait past the budget
        failed = False
        for via, future in zip(pair, futures, strict=True):  # in order: left is preferred over right
            if future not in done:
                continue  # still running when time ran out; stays untried
            try:
                profile = future.result()[0]
            except NoRoute:
                search.untried.remove(via)  # a definite answer: no truck road near this point
                continue
            except PlanError as error:
                logger.warning("Via route attempt failed: %s", error.message)
                failed = True  # busy, refused or unreadable: may work later, so it stays untried
                continue
            search.untried.remove(via)
            if profile.travel_time_s > MAX_DETOUR_RATIO * main.travel_time_s:
                logger.info(
                    "Via route rejected: %.0f%% slower",
                    100 * (profile.travel_time_s / main.travel_time_s - 1),
                )
                continue
            shape = RouteShape(profile.points)
            if len(search.routes) < ROUTE_COUNT and all(are_distinct(shape, other) for other in shapes):
                search.routes.append(FoundRoute(profile, via=True))
                shapes.append(shape)
        if failed:
            return "failed"  # don't spend more requests on a routing service that isn't answering
        if pending:
            return "out_of_time"
    return "complete"
