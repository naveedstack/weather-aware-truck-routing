"""Risk classification: every boundary of the settled ranges, the load rules and worst-of."""

import math

import pytest

from trips.domain.risk import (
    RiskLevel,
    apply_load_rules,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    leading_condition,
    load_rule_text,
)

L, M, H, S, NT = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


def below(value: float) -> float:
    """The largest float smaller than value."""
    return math.nextafter(value, -math.inf)


def above(value: float) -> float:
    """The smallest float larger than value."""
    return math.nextafter(value, math.inf)


@pytest.mark.parametrize(
    ("mph", "level"),
    [
        (0, L),
        (24.9, L),
        (below(25), L),
        (25, M),
        (25.1, M),
        (34.6, M),  # between the table's whole-number ranges
        (below(35), M),
        (35, H),
        (44.9, H),
        (below(45), H),
        (45, S),
        (54.9, S),
        (below(55), S),
        (55, NT),
        (above(55), NT),
        (150, NT),
    ],
)
def test_wind_levels(mph, level):
    assert classify_wind(mph) is level


@pytest.mark.parametrize(
    ("in_per_hr", "level"),
    [
        (0, L),
        (0.099, L),
        (below(0.10), L),
        (0.10, M),
        (0.249, M),
        (below(0.25), M),
        (0.25, H),  # in both Moderate and High in the original table: goes to the higher level
        (0.499, H),
        (below(0.50), H),
        (0.50, S),  # in both High and Severe in the original table
        (0.999, S),
        (1.00, S),  # "0.50 to 1.00" includes 1.00
        (above(1.00), NT),
        (1.001, NT),
        (5.0, NT),
    ],
)
def test_rain_levels(in_per_hr, level):
    assert classify_rain(in_per_hr) is level


@pytest.mark.parametrize(
    ("in_per_hr", "level"),
    [
        (0, L),
        (0.499, L),
        (below(0.5), L),
        (0.5, M),
        (0.999, M),
        (below(1.0), M),
        (1.0, H),
        (1.999, H),
        (below(2.0), H),
        (2.0, S),
        (2.999, S),
        (3.0, S),  # "2.0 to 3.0" includes 3.0
        (above(3.0), NT),
        (3.001, NT),
    ],
)
def test_snow_levels(in_per_hr, level):
    assert classify_snow(in_per_hr) is level


@pytest.mark.parametrize(
    ("mph", "load_lb", "level"),
    [
        # 35 up to 45 mph with a load above 40,000 lb -> Severe
        (34.9, 40_001, M),  # no load rule below 35 mph
        (35, 40_000, H),  # exactly 40,000 is not above it
        (35, 40_000.01, S),
        (35, 40_001, S),
        (40, 35_000, H),  # load not heavy enough
        (44.9, 40_001, S),
        (below(45), 40_001, S),
        # 45 up to 55 mph with a load above 30,000 lb -> No Travel
        (45, 30_000, S),  # exactly 30,000 is not above it
        (45, 30_000.01, NT),
        (45, 30_001, NT),
        (50, 45_000, NT),  # above both thresholds: the 45-55 rule applies
        (54.9, 30_001, NT),
        (54.9, 30_000, S),
        # 55 mph and above is No Travel for any load
        (55, 0, NT),
        (60, 80_000, NT),
        # light wind is never raised by load
        (20, 80_000, L),
        (30, 80_000, M),
    ],
)
def test_load_rules(mph, load_lb, level):
    assert apply_load_rules(classify_wind(mph), load_lb) is level
    assert assess(mph, 0, 0, load_lb).level is level


def test_load_rules_only_touch_wind():
    assert assess(10, 0.6, 0, 50_000).level is S
    assert assess(10, 0, 2.5, 50_000).level is S


@pytest.mark.parametrize(
    ("wind", "rain", "snow", "load", "level"),
    [
        (0, 0, 0, 0, L),
        (5, 0.3, 0, 0, H),
        (30, 0, 2.5, 0, S),
        (40, 0.3, 0, 41_000, S),  # wind becomes Severe through the load rule; rain is High
        (40, 0, 3.5, 41_000, NT),  # the load rule never lowers anything
        (40, 0.3, 0, 0, H),  # equal levels
        (24.9, 0.099, 0.499, 80_000, L),
    ],
)
def test_overall_level_is_worst_of_wind_rain_snow(wind, rain, snow, load, level):
    assert assess(wind, rain, snow, load).level is level


def test_assessment_reports_each_condition_and_load_rule():
    result = assess(47, 0.3, 0.6, 35_000)
    assert result.wind is NT
    assert result.rain is H
    assert result.snow is M
    assert result.load_rule_applied
    assert result.level is NT

    plain = assess(47, 0.3, 0.6, 25_000)
    assert plain.wind is S
    assert not plain.load_rule_applied
    assert plain.level is S


@pytest.mark.parametrize(
    ("wind", "rain", "snow", "load", "level"),
    [
        (None, 0.2, 0, 0, None),  # wind could be anything: No data
        (None, 1.2, None, 0, NT),  # rain alone already makes it No Travel
        (60, None, None, 0, NT),
        (50, None, 0, 31_000, NT),  # known through the load rule
        (50, None, 0, 20_000, None),  # Severe so far, but rain could be worse
        (None, None, None, 0, None),
        (10, 0, None, 0, None),
    ],
)
def test_missing_values(wind, rain, snow, load, level):
    assert assess(wind, rain, snow, load).level is level


def test_labels_and_scores():
    assert [level.label for level in RiskLevel] == ["Low", "Moderate", "High", "Severe", "No Travel"]
    assert [int(level) for level in RiskLevel] == [0, 1, 2, 3, 4]


def test_load_rule_text():
    assert (
        load_rule_text(assess(50, 0, 0, 31_000))
        == "Wind of 45 up to 55 mph with a load over 30,000 lb is No Travel."
    )
    assert (
        load_rule_text(assess(40, 0, 0, 41_000))
        == "Wind of 35 up to 45 mph with a load over 40,000 lb is Severe."
    )
    assert load_rule_text(assess(40, 0, 0, 40_000)) is None
    assert load_rule_text(assess(60, 0, 0, 80_000)) is None  # 55 mph and above is No Travel for any load


def test_leading_condition_names_what_set_the_level():
    # Rain is the worst of the three, so rain is what made the checkpoint High.
    assert leading_condition(assess(10.0, 0.3, 0.0, 35_000)) == "rain"
    assert leading_condition(assess(40.0, 0.0, 0.0, 10_000)) == "wind"
    assert leading_condition(assess(5.0, 0.0, 1.5, 35_000)) == "snow"
    # Wind raised by a load rule still counts as wind.
    assert leading_condition(assess(40.0, 0.0, 0.0, 45_000)) == "wind"
    # Ties go to wind, then rain, then snow.
    assert leading_condition(assess(30.0, 0.15, 0.6, 35_000)) == "wind"
    # No level, so nothing to blame.
    assert leading_condition(assess(None, 0.0, 0.0, 35_000)) is None
