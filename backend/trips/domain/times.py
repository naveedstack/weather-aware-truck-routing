"""Time helpers. All trip math happens in UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


def require_aware(moment: datetime) -> datetime:
    """Return the moment in UTC, refusing naive datetimes (their time zone would be a guess)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("datetime must include a time zone offset")
    return moment.astimezone(UTC)


def nearest_hour(moment: datetime) -> datetime:
    """The whole UTC hour nearest to a moment. Exactly half past rounds up to the next hour."""
    utc = require_aware(moment)
    hour = utc.replace(minute=0, second=0, microsecond=0)
    return hour + HOUR if utc - hour >= HOUR / 2 else hour


def nearest_minute(moment: datetime) -> datetime:
    """The whole UTC minute nearest to a moment. Exactly half a minute rounds up."""
    utc = require_aware(moment)
    minute = utc.replace(second=0, microsecond=0)
    return minute + MINUTE if utc - minute >= MINUTE / 2 else minute


def eta_after(departure: datetime, elapsed_s: float) -> datetime:
    """The time `elapsed_s` seconds of driving after `departure`, to the nearest minute. ETAs are
    shown to the minute, so the forecast hour is chosen from the minute that is shown, and the
    (whole-minute) departure plus the shown travel time is the shown arrival."""
    return nearest_minute(require_aware(departure) + timedelta(seconds=elapsed_s))


def epoch_seconds(moment: datetime) -> int:
    """Whole seconds since 1970-01-01 UTC, used as the key for forecast hours."""
    return int(require_aware(moment).timestamp())
