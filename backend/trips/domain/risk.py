"""Weather risk levels and the load rules from the assignment's requirements.

The requirements table leaves boundary values open (is 0.25 in/hr Moderate or High? is
34.6 mph anything?). We use the ranges recorded in README "Assumptions", which keep the
table's numbers: "A up to B" includes A but not B, and "A to B" includes both.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    """Risk levels from best to worst. The value is the score used for average risk."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


# Lower bound of every level above Low, worst level first:
# (level, bound, whether a value exactly equal to the bound belongs to that level).
Thresholds = tuple[tuple[RiskLevel, float, bool], ...]

WIND_MPH_THRESHOLDS: Thresholds = (
    (RiskLevel.NO_TRAVEL, 55.0, True),  # 55 and above
    (RiskLevel.SEVERE, 45.0, True),  # 45 up to 55
    (RiskLevel.HIGH, 35.0, True),  # 35 up to 45
    (RiskLevel.MODERATE, 25.0, True),  # 25 up to 35; below 25 is Low
)
RAIN_IN_HR_THRESHOLDS: Thresholds = (
    (RiskLevel.NO_TRAVEL, 1.00, False),  # above 1.00
    (RiskLevel.SEVERE, 0.50, True),  # 0.50 to 1.00
    (RiskLevel.HIGH, 0.25, True),  # 0.25 up to 0.50
    (RiskLevel.MODERATE, 0.10, True),  # 0.10 up to 0.25; below 0.10 is Low
)
SNOW_IN_HR_THRESHOLDS: Thresholds = (
    (RiskLevel.NO_TRAVEL, 3.0, False),  # above 3.0
    (RiskLevel.SEVERE, 2.0, True),  # 2.0 to 3.0
    (RiskLevel.HIGH, 1.0, True),  # 1.0 up to 2.0
    (RiskLevel.MODERATE, 0.5, True),  # 0.5 up to 1.0; below 0.5 is Low
)

# Load rules. Wind of 55 mph or more is already No Travel for any load (see the wind table).
NO_TRAVEL_LOAD_LB = 30_000  # Severe wind (45 up to 55 mph) with a load above this -> No Travel
SEVERE_LOAD_LB = 40_000  # High wind (35 up to 45 mph) with a load above this -> Severe


def _classify(value: float, thresholds: Thresholds) -> RiskLevel:
    for level, bound, includes_bound in thresholds:
        if value > bound or (includes_bound and value == bound):
            return level
    return RiskLevel.LOW


def classify_wind(mph: float) -> RiskLevel:
    """Level for a sustained wind speed in mph, before the load rules."""
    return _classify(mph, WIND_MPH_THRESHOLDS)


def classify_rain(in_per_hr: float) -> RiskLevel:
    """Level for a liquid rain rate in inches per hour."""
    return _classify(in_per_hr, RAIN_IN_HR_THRESHOLDS)


def classify_snow(in_per_hr: float) -> RiskLevel:
    """Level for a snowfall rate in inches per hour."""
    return _classify(in_per_hr, SNOW_IN_HR_THRESHOLDS)


def apply_load_rules(wind_level: RiskLevel, load_lb: float) -> RiskLevel:
    """Raise the wind level for heavy loads. The rules never lower a level."""
    if wind_level is RiskLevel.SEVERE and load_lb > NO_TRAVEL_LOAD_LB:
        return RiskLevel.NO_TRAVEL
    if wind_level is RiskLevel.HIGH and load_lb > SEVERE_LOAD_LB:
        return RiskLevel.SEVERE
    return wind_level


@dataclass(frozen=True)
class Assessment:
    """Risk at one place and hour. ``None`` anywhere means "No data"."""

    level: RiskLevel | None
    wind: RiskLevel | None  # after the load rules
    rain: RiskLevel | None
    snow: RiskLevel | None
    load_rule_applied: bool


NO_DATA = Assessment(level=None, wind=None, rain=None, snow=None, load_rule_applied=False)


def load_rule_text(assessment: Assessment) -> str | None:
    """The load rule that raised the wind level, in words, or None if none did."""
    if not assessment.load_rule_applied:
        return None
    if assessment.wind is RiskLevel.NO_TRAVEL:
        return f"Wind of 45 up to 55 mph with a load over {NO_TRAVEL_LOAD_LB:,} lb is No Travel."
    return f"Wind of 35 up to 45 mph with a load over {SEVERE_LOAD_LB:,} lb is Severe."


def leading_condition(assessment: Assessment) -> str | None:
    """Which of wind, rain or snow set the level: what to blame for a checkpoint's or a heatmap
    cell's colour. None when there is no level. Wind wins a tie, then rain, then snow."""
    if assessment.level is None:
        return None
    for name, level in (("wind", assessment.wind), ("rain", assessment.rain), ("snow", assessment.snow)):
        if level is assessment.level:
            return name
    return None


def assess(
    wind_mph: float | None,
    rain_in_per_hr: float | None,
    snow_in_per_hr: float | None,
    load_lb: float,
) -> Assessment:
    """Combine wind (after the load rules), rain and snow into one level: the worst of the three.

    A missing value makes the result "No data", unless a known value is already No Travel,
    because then the worst level can't be anything else.
    """
    base_wind = None if wind_mph is None else classify_wind(wind_mph)
    wind = None if base_wind is None else apply_load_rules(base_wind, load_lb)
    rain = None if rain_in_per_hr is None else classify_rain(rain_in_per_hr)
    snow = None if snow_in_per_hr is None else classify_snow(snow_in_per_hr)

    known = [level for level in (wind, rain, snow) if level is not None]
    if len(known) == 3:
        level: RiskLevel | None = max(known)
    elif RiskLevel.NO_TRAVEL in known:
        level = RiskLevel.NO_TRAVEL
    else:
        level = None
    return Assessment(
        level=level,
        wind=wind,
        rain=rain,
        snow=snow,
        load_rule_applied=wind is not None and wind is not base_wind,
    )
