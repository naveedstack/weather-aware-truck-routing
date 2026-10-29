from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from trips.domain.times import epoch_seconds, eta_after, nearest_hour, require_aware


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (utc(2026, 10, 26, 8, 0), utc(2026, 10, 26, 8, 0)),
        (utc(2026, 10, 26, 8, 29, 59, 999_999), utc(2026, 10, 26, 8, 0)),
        (utc(2026, 10, 26, 8, 30), utc(2026, 10, 26, 9, 0)),  # half past rounds up
        (utc(2026, 10, 26, 8, 30, 1), utc(2026, 10, 26, 9, 0)),
        (utc(2026, 10, 26, 9, 30), utc(2026, 10, 26, 10, 0)),  # not banker's rounding
        (utc(2026, 10, 26, 23, 30), utc(2026, 10, 27, 0, 0)),  # crosses midnight
    ],
)
def test_nearest_hour(moment, expected):
    assert nearest_hour(moment) == expected


def test_nearest_hour_converts_other_zones_to_utc():
    chicago_cdt = timezone(timedelta(hours=-5))
    assert nearest_hour(datetime(2026, 10, 26, 8, 40, tzinfo=chicago_cdt)) == utc(2026, 10, 26, 14, 0)


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError):
        nearest_hour(datetime(2026, 10, 26, 8, 0))
    with pytest.raises(ValueError):
        require_aware(datetime(2026, 10, 26, 8, 0))


@pytest.mark.parametrize(
    ("elapsed_s", "expected"),
    [
        (0, utc(2026, 10, 26, 8, 0)),
        (29.999, utc(2026, 10, 26, 8, 0)),
        (30, utc(2026, 10, 26, 8, 1)),  # half a minute rounds up
        (42_699, utc(2026, 10, 26, 19, 52)),  # 711 min 39 s: the card shows 712 min, arriving at 19:52
        (91 * 60 + 29.5, utc(2026, 10, 26, 9, 31)),
    ],
)
def test_etas_are_rounded_to_the_nearest_minute(elapsed_s, expected):
    assert eta_after(utc(2026, 10, 26, 8, 0), elapsed_s) == expected


def test_the_forecast_hour_follows_the_eta_that_is_shown():
    # 8:29:40 is shown as 8:30, so it takes the 9:00 forecast, as a shown 8:30 should.
    eta = eta_after(utc(2026, 10, 26, 8, 0), 29 * 60 + 40)
    assert eta == utc(2026, 10, 26, 8, 30)
    assert nearest_hour(eta) == utc(2026, 10, 26, 9, 0)


def test_etas_are_in_utc():
    chicago_cdt = timezone(timedelta(hours=-5))
    eta = eta_after(datetime(2026, 10, 26, 8, 0, tzinfo=chicago_cdt), 60)
    assert eta == utc(2026, 10, 26, 13, 1)
    assert eta.tzinfo is UTC
    # 00:30 CDT plus two hours of driving crosses the end of daylight saving time: 07:30 UTC.
    chicago = ZoneInfo("America/Chicago")
    assert eta_after(datetime(2026, 11, 1, 0, 30, tzinfo=chicago), 7200) == utc(2026, 11, 1, 7, 30)
    with pytest.raises(ValueError):
        eta_after(datetime(2026, 10, 26, 8, 0), 60)


def test_epoch_seconds():
    assert epoch_seconds(utc(2026, 10, 24, 12, 0)) == 1_792_843_200


def test_half_hour_offsets_round_in_utc():
    newfoundland = timezone(timedelta(hours=-3, minutes=-30))
    # 09:00 at -03:30 is 12:30 UTC, which rounds up to 13:00 UTC.
    assert nearest_hour(datetime(2026, 11, 2, 9, 0, tzinfo=newfoundland)) == utc(2026, 11, 2, 13, 0)


def test_repeated_hour_at_the_end_of_daylight_saving_time():
    new_york = ZoneInfo("America/New_York")
    # 01:30 happens twice on 2026-11-01: first at 05:30 UTC (EDT), then at 06:30 UTC (EST).
    assert nearest_hour(datetime(2026, 11, 1, 1, 30, fold=0, tzinfo=new_york)) == utc(2026, 11, 1, 6, 0)
    assert nearest_hour(datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=new_york)) == utc(2026, 11, 1, 7, 0)
