"""TomTom Geocoding and Routing.

Routing uses the v1 "TomTom Maps" API because TomTom's newer Orbis routing has no truck mode.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.cache import cache

from ..domain.alternatives import VIA_RADIUS_M
from ..domain.geo import LatLon
from ..domain.profile import RouteProfile, TimingAnchor, build_profile
from ..errors import NoRoute, PlaceNotFound, RoutingTimeout, RoutingUnavailable
from .http import CONNECT_TIMEOUT_S, is_timeout, redact, session

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{query}.json"
SEARCH_URL = "https://api.tomtom.com/search/2/search/{query}.json"
ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{locations}/json"
GEOCODE_TIMEOUT_S = 6.0
GEOCODE_CACHE_S = 24 * 3600
SUGGEST_TIMEOUT_S = 4.0  # suggestions are only useful while the user is still typing
SUGGESTIONS = 5  # city names suggested for a field
SUGGEST_RESULTS = 10  # results asked of TomTom, so that duplicates still leave five names
# Places are searched in the US, Canada and Mexico: the app's units and weight limit are American,
# and without a filter a ZIP code such as 75201 matches a postal area on another continent.
GEOCODE_COUNTRIES = "US,CA,MX"
NO_ROUTE_CODES = {"NO_ROUTE_FOUND", "MAP_MATCHING_FAILURE"}


@dataclass(frozen=True)
class Place:
    name: str  # TomTom's address for the match, e.g. "Dallas, TX"
    position: LatLon


def _cache_key(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256(repr(parts).encode()).hexdigest()
    return f"tomtom:{prefix}:{digest}"


def _detail(response: requests.Response) -> tuple[str, str]:
    """TomTom's error code and message, from whichever error shape the response uses."""
    try:
        body = response.json()
    except ValueError:
        return "", response.text[:200]
    detail = body.get("detailedError") or {}
    legacy = body.get("error") or {}
    message = detail.get("message") or body.get("errorText") or legacy.get("description") or ""
    return str(detail.get("code") or ""), str(message)


def _get(url: str, params: list[tuple[str, str]], timeout_s: float, service: str) -> dict[str, Any]:
    """GET a TomTom endpoint and return its JSON, turning every failure into a clear PlanError."""
    try:
        response = session().get(
            url, params=[*params, ("key", settings.TOMTOM_API_KEY)], timeout=(CONNECT_TIMEOUT_S, timeout_s)
        )
    except requests.RequestException as error:
        if is_timeout(error):
            logger.warning("TomTom %s timed out after %.0f s", service, timeout_s)
            raise RoutingTimeout(
                f"The {service} service took too long to answer. Please try again."
            ) from None
        logger.warning("TomTom %s request failed: %s", service, redact(str(error)))
        raise RoutingUnavailable(f"Couldn't reach the {service} service. Please try again.") from None

    if response.status_code == 200:
        try:
            return response.json()
        except ValueError:
            logger.warning("TomTom %s returned invalid JSON", service)
            raise RoutingUnavailable(f"The {service} service sent an unreadable answer.") from None

    code, message = _detail(response)
    logger.warning("TomTom %s error %s %s: %s", service, response.status_code, code, redact(message))
    if response.status_code == 400 and code in NO_ROUTE_CODES:
        raise NoRoute("No truck route found between these places.")
    if response.status_code in (401, 403):
        raise RoutingUnavailable(
            f"The {service} service refused the request. The server's TomTom key may be missing, "
            "invalid or out of quota."
        )
    if response.status_code == 429:
        raise RoutingUnavailable(f"The {service} service is busy. Please try again in a moment.")
    raise RoutingUnavailable(
        f"The {service} service couldn't handle this request (error {response.status_code})."
    )


def geocode(query: str, field: str) -> Place:
    """TomTom's best match for a free-text place, such as "Dallas, TX". Results are cached."""
    text = " ".join(query.split())
    key = _cache_key("geocode", text.casefold())
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _get(
        GEOCODE_URL.format(query=quote(text, safe="")),
        [("limit", "1"), ("language", "en-US"), ("countrySet", GEOCODE_COUNTRIES)],
        GEOCODE_TIMEOUT_S,
        "place search",
    )
    results = data.get("results") or []
    if not results:
        raise PlaceNotFound(f'Couldn\'t find "{text}". Try a city and state, like "Dallas, TX".', field=field)
    top = results[0]
    position = top.get("position") or {}
    try:
        place = Place(
            name=(top.get("address") or {}).get("freeformAddress") or text,
            position=(float(position["lat"]), float(position["lon"])),
        )
    except (KeyError, TypeError, ValueError):
        raise RoutingUnavailable("The place search service sent an unreadable answer.") from None
    cache.set(key, place, GEOCODE_CACHE_S)
    return place


def suggest_places(query: str) -> list[str]:
    """Up to five cities for partly typed text, best match first: "Dal" gives "Dallas, TX",
    "Dale, VA" and so on. TomTom's fuzzy search with typeahead reads the last word as unfinished
    and forgives typos. Only cities are suggested, in the countries places are searched in.
    Results are cached."""
    text = " ".join(query.split())
    key = _cache_key("suggest", text.casefold())
    cached = cache.get(key)
    if cached is not None:
        return cached
    data = _get(
        SEARCH_URL.format(query=quote(text, safe="")),
        [
            ("typeahead", "true"),
            ("idxSet", "Geo"),
            ("entityTypeSet", "Municipality"),
            ("countrySet", GEOCODE_COUNTRIES),
            ("limit", str(SUGGEST_RESULTS)),
            ("language", "en-US"),
        ],
        SUGGEST_TIMEOUT_S,
        "place search",
    )
    names: list[str] = []
    for result in data.get("results") or []:
        name = _city_name(result.get("address") or {})
        if name and name.casefold() not in {known.casefold() for known in names}:
            names.append(name)
        if len(names) == SUGGESTIONS:
            break
    cache.set(key, names, GEOCODE_CACHE_S)
    return names


def _city_name(address: dict[str, Any]) -> str | None:
    """The city and its state or province, such as "Dallas, TX". The name is put together from its
    parts because TomTom writes Canadian places without the comma ("Toronto ON")."""
    city = address.get("municipality")
    region = address.get("countrySubdivision")
    if isinstance(city, str) and city and isinstance(region, str) and region:
        return f"{city}, {region}"
    name = address.get("freeformAddress")
    return name if isinstance(name, str) and name else None


def _route_profile(route: dict[str, Any]) -> RouteProfile:
    """Distance and time at every point of one TomTom route.

    Timing comes from the route's per-point progress data, or from its guidance instructions if
    progress is missing. Point indexes refer to all legs' points joined in order.
    """
    points = [(float(p["latitude"]), float(p["longitude"])) for leg in route["legs"] for p in leg["points"]]
    summary = route["summary"]
    anchors = [
        TimingAnchor(int(p["pointIndex"]), float(p["travelTimeInSeconds"]), p.get("distanceInMeters"))
        for p in route.get("progress") or []
        if "pointIndex" in p and "travelTimeInSeconds" in p
    ]
    if not anchors:
        anchors = [
            TimingAnchor(int(i["pointIndex"]), float(i["travelTimeInSeconds"]), i.get("routeOffsetInMeters"))
            for i in (route.get("guidance") or {}).get("instructions") or []
            if "pointIndex" in i and "travelTimeInSeconds" in i
        ]
        logger.warning("TomTom route without progress data; using %d instruction times", len(anchors))
    return build_profile(
        points, anchors, float(summary["lengthInMeters"]), float(summary["travelTimeInSeconds"])
    )


def calculate_routes(
    origin: LatLon,
    destination: LatLon,
    departure: datetime,
    *,
    alternatives: int,
    timeout_s: float,
    via: LatLon | None = None,
) -> list[RouteProfile]:
    """Truck routes from TomTom, best first: the main route and up to `alternatives` others.

    `via` adds a circle waypoint (a point the route passes near, without a stop or an extra leg).
    """
    stops = [f"{origin[0]:.6f},{origin[1]:.6f}"]
    if via is not None:
        stops.append(f"circle({via[0]:.6f},{via[1]:.6f},{VIA_RADIUS_M})")
    stops.append(f"{destination[0]:.6f},{destination[1]:.6f}")
    params = [
        ("travelMode", "truck"),
        ("vehicleCommercial", "true"),
        ("departAt", departure.astimezone(UTC).isoformat(timespec="seconds")),
        ("maxAlternatives", str(alternatives)),
        ("extendedRouteRepresentation", "distance"),
        ("extendedRouteRepresentation", "travelTime"),
        ("instructionsType", "coded"),  # only used when a route has no progress data
    ]
    data = _get(ROUTE_URL.format(locations=":".join(stops)), params, timeout_s, "routing")
    try:
        profiles = [_route_profile(route) for route in data.get("routes") or []]
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("Unexpected TomTom route data: %r", error)
        raise RoutingUnavailable("The routing service sent an unreadable answer.") from None
    if not profiles:
        raise NoRoute("No truck route found between these places.")
    return profiles
