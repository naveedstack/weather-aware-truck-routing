"""Validation of the trip form sent to POST /api/plan/."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from django.utils import timezone
from rest_framework import serializers

from .clients.openmeteo import last_forecast_hour
from .domain.times import nearest_minute
from .planner import DEFAULT_INTERVAL_MI, TripRequest

MAX_LOAD_LB = 80_000  # the US federal gross weight limit, as a sanity bound for the cargo
DEPARTURE_GRACE = timedelta(minutes=15)  # time to fill in the form
MIN_SUGGEST_CHARS = 3  # letters or digits typed before cities are suggested


class AwareDateTimeField(serializers.DateTimeField):
    """An ISO 8601 date and time that must include its time zone offset; returned in UTC."""

    default_error_messages: ClassVar[dict[str, str]] = {
        "naive": "Include a time zone offset, for example 2026-10-25T08:00:00-05:00.",
    }

    def enforce_timezone(self, value: datetime) -> datetime:
        if timezone.is_naive(value):
            self.fail("naive")
        try:
            return value.astimezone(UTC)
        except OverflowError:  # e.g. year 9999 with a negative offset
            self.fail("overflow")


class PoundsField(serializers.FloatField):
    """A weight in pounds. DRF already rejects NaN and infinity; true and false aren't weights."""

    def to_internal_value(self, data: object) -> float:
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class TripRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200, trim_whitespace=True)
    destination = serializers.CharField(max_length=200, trim_whitespace=True)
    departure = AwareDateTimeField()
    load_lb = PoundsField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=DEFAULT_INTERVAL_MI)

    def validate_departure(self, value: datetime) -> datetime:
        now = self.context.get("now") or datetime.now(UTC)
        if value < now - DEPARTURE_GRACE:
            raise serializers.ValidationError("Departure is in the past.")
        latest = last_forecast_hour(now)
        if value > latest:
            raise serializers.ValidationError(
                f"Departure must be by {latest:%b} {latest.day}, {latest:%H:%M} UTC, the end of the weather "
                "forecast."
            )
        # Plans work to the minute (ETAs, the arrival, hour 0 of the slider), so the departure does too.
        return nearest_minute(value)

    def validate(self, attrs: dict) -> dict:
        def same(text: str) -> str:
            return " ".join(text.split()).casefold()

        if same(attrs["origin"]) == same(attrs["destination"]):
            raise serializers.ValidationError({"destination": "Origin and destination are the same."})
        return attrs

    def trip_request(self) -> TripRequest:
        data = self.validated_data
        return TripRequest(
            origin=data["origin"],
            destination=data["destination"],
            departure=data["departure"],
            load_lb=data["load_lb"],
            interval_mi=int(data["interval_mi"]),
        )


class PlaceQuerySerializer(serializers.Serializer):
    """The text typed so far in the form's From or To field, for GET /api/places/?q=..."""

    q = serializers.CharField(max_length=200, trim_whitespace=True)

    def validate_q(self, value: str) -> str:
        # Text that is mostly punctuation would get random cities back from TomTom.
        if sum(character.isalnum() for character in value) < MIN_SUGGEST_CHARS:
            raise serializers.ValidationError(f"Type at least {MIN_SUGGEST_CHARS} letters or digits.")
        return value
