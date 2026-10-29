"""Problems a plan request can run into. Each carries the HTTP status and message the API returns."""

from __future__ import annotations


class PlanError(Exception):
    status = 400
    code = "invalid_request"

    def __init__(self, message: str, *, field: str | None = None, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field  # the form field the message belongs to, if any
        self.retry_after_s = retry_after_s


class PlaceNotFound(PlanError):
    status = 422
    code = "place_not_found"


class SamePlace(PlanError):
    status = 422
    code = "same_place"


class NoRoute(PlanError):
    status = 422
    code = "no_route"


class RoutingUnavailable(PlanError):
    status = 502
    code = "routing_unavailable"


class RoutingTimeout(RoutingUnavailable):
    """TomTom didn't answer in time. The planner can fall back to a quicker request."""


class WeatherRateLimited(PlanError):
    status = 503
    code = "weather_rate_limited"


class WeatherUnavailable(PlanError):
    status = 502
    code = "weather_unavailable"
