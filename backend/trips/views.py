"""The HTTP API. Every error has the same JSON shape: {"error": {"code", "message", ...}}."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .clients import tomtom
from .errors import PlanError
from .planner import plan_trip
from .presenters import plan_to_json
from .serializers import PlaceQuerySerializer, TripRequestSerializer

logger = logging.getLogger(__name__)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


def _failure(error: PlanError) -> Response:
    headers = {"Retry-After": str(error.retry_after_s)} if error.retry_after_s else None
    body = _error(error.code, error.message, **({"field": error.field} if error.field else {}))
    return Response(body, status=error.status, headers=headers)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Every error raised in a view, in the API's error shape: DRF's own (bad JSON, wrong method...)
    and anything unexpected, which is logged and returned as a JSON 500."""
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unexpected error", exc_info=exc)
        return Response(_error("internal_error", "Something went wrong while planning the trip."), status=500)
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    response.data = _error(getattr(exc, "default_code", "error"), str(detail or exc))
    return response


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness check. Calls nothing upstream."""
    return Response({"status": "ok"})


@api_view(["POST"])
def plan(request: Request) -> Response:
    """Plan a trip. See trips/presenters.py for the response."""
    form = TripRequestSerializer(data=request.data, context={"now": datetime.now(UTC)})
    if not form.is_valid():
        fields = {name: str(messages[0]) for name, messages in form.errors.items()}
        general = fields.pop("non_field_errors", None)  # e.g. a body that isn't a JSON object
        message = general or "Please check the highlighted fields."
        return Response(_error("invalid_input", message, fields=fields), status=400)
    try:
        trip = plan_trip(form.trip_request())
    except PlanError as error:
        return _failure(error)
    return Response(plan_to_json(trip))


@api_view(["GET"])
def places(request: Request) -> Response:
    """Cities for what's typed so far in the form's From or To field, best match first:
    {"places": [{"name": "Dallas, TX"}, ...]}, at most five."""
    form = PlaceQuerySerializer(data=request.query_params)
    if not form.is_valid():
        message = str(form.errors["q"][0])
        return Response(_error("invalid_input", message, fields={"q": message}), status=400)
    try:
        names = tomtom.suggest_places(form.validated_data["q"])
    except PlanError as error:
        return _failure(error)
    return Response({"places": [{"name": name} for name in names]})
