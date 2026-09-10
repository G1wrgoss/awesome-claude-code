"""Scoring tests.

The Brier and calibration cases below carry expected values computed by hand and shown
longhand in the docstrings, because these two calculations are where a subtle error would be
both easy to make and fatal to the project's credibility.
"""

from __future__ import annotations

import math

import pytest
from helpers import make
from tracker import scoring
from tracker.scoring import (
    BASELINE_BRIER,
    brier_score,
    bucket_index,
    calibration,
    rolling_brier,
    skill_score,
    standing,
    wilson_interval,
)

# --------------------------------------------------------------------------------------
# Brier score
# --------------------------------------------------------------------------------------

def test_brier_score_hand_computed():
    """Three predictions, worked by hand:

        80% -> TRUE   (0.80 - 1)^2 = (-0.20)^2 = 0.04
        30% -> FALSE  (0.30 - 0)^2 = ( 0.30)^2 = 0.09
        60% -> FALSE  (0.60 - 0)^2 = ( 0.60)^2 = 0.36
                                     sum       = 0.49
                                     / 3       = 0.16333333...
    """
    predictions = [make(80, True), make(30, False), make(60, False)]
    assert brier_score(predictions) == pytest.approx(0.49 / 3)
    assert brier_score(predictions) == pytest.approx(0.1633333333333333, abs=1e-12)


def test_brier_score_perfect_and_worst():
    """A perfect forecaster scores 0; a maximally wrong one scores 1."""
    assert brier_score([make(100, True), make(0, False)]) == pytest.approx(0.0)
    assert brier_score([make(0, True), make(100, False)]) == pytest.approx(1.0)


def test_brier_score_of_all_fifties_equals_the_baseline():
    """(0.5 - 0)^2 == (0.5 - 1)^2 == 0.25, so a pure coin-flipper lands exactly on baseline."""
    predictions = [make(50, True), make(50, False), make(50, True)]
    assert brier_score(predictions) == pytest.approx(BASELINE_BRIER)


def test_brier_score_is_none_when_nothing_resolved():
    """None, never 0.0 -- an empty record must not be able to render as a perfect score."""
    assert brier_score([make(70), make(20)]) is None
    assert brier_score([]) is None


def test_brier_score_ignores_open_predictions():
    open_one = make(99)
    resolved = [make(80, True), make(30, False), make(60, False)]
    assert brier_score([*resolved, open_one]) == pytest.approx(0.49 / 3)


# --------------------------------------------------------------------------------------
# Skill against baseline
# --------------------------------------------------------------------------------------

def test_skill_score_hand_computed():
    """1 - (0.163333... / 0.25) = 1 - 0.653333... = 0.346666..."""
    brier = 0.49 / 3
    assert skill_score(brier) == pytest.approx(0.3466666666666667, abs=1e-12)


def test_skill_score_is_zero_on_the_baseline_and_negative_below_it():
    assert skill_score(BASELINE_BRIER) == pytest.approx(0.0)
    assert skill_score(0.5) == pytest.approx(-1.0)   # twice the baseline error
    assert skill_score(0.0) == pytest.approx(1.0)    # perfect
    assert skill_score(None) is None


# --------------------------------------------------------------------------------------
# Bucketing
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "probability,expected",
    [(0, 0), (9, 0), (10, 1), (19, 1), (50, 5), (89, 8), (90, 9), (99, 9), (100, 9)],
)
def test_bucket_edges_are_half_open_upward_with_100_folded_into_the_top(probability, expected):
    assert bucket_index(probability) == expected


def test_bucket_index_rejects_out_of_range():
    with pytest.raises(ValueError):
        bucket_index(101)
    with pytest.raises(ValueError):
        bucket_index(-1)


def test_calibration_hand_computed():
    """Four predictions in the 70-80 bucket, three of which came true.

        stated mean = (0.70 + 0.75 + 0.70 + 0.78) / 4 = 2.93 / 4 = 0.7325
        hit rate    = 3 / 4                           = 0.75
    """
    predictions = [make(70, True), make(75, True), make(70, False), make(78, True)]
    buckets = calibration(predictions)
    bucket = buckets[7]
    assert (bucket.low, bucket.high) == (70, 80)
    assert bucket.count == 4
    assert bucket.hits == 3
    assert bucket.mean_stated == pytest.approx(0.7325)
    assert bucket.hit_rate == pytest.approx(0.75)


def test_calibration_returns_every_bucket_including_empty_ones():
    """Gaps in the record must stay visible rather than being closed up."""
    buckets = calibration([make(75, True)])
    assert len(buckets) == 10
    assert [b.count for b in buckets] == [0, 0, 0, 0, 0, 0, 0, 1, 0, 0]
    assert buckets[0].empty and buckets[0].hit_rate is None


def test_calibration_ignores_open_predictions():
    buckets = calibration([make(75, True), make(75), make(75)])
    assert buckets[7].count == 1


def test_thin_buckets_are_flagged():
    """A bucket below the threshold is marked, so it cannot be presented as meaningful."""
    four = calibration([make(75, True) for _ in range(4)])[7]
    five = calibration([make(75, True) for _ in range(5)])[7]
    assert four.thin is True
    assert five.thin is False
    assert calibration([])[7].thin is False  # empty is not "thin", it is absent


# --------------------------------------------------------------------------------------
# Wilson intervals
# --------------------------------------------------------------------------------------

def test_wilson_interval_zero_hits_hand_derived():
    """With p-hat = 0 the Wilson centre and margin are algebraically equal:

        centre = (z^2 / 2n) / (1 + z^2/n)
        margin = z/(1 + z^2/n) * sqrt(0 + z^2/4n^2) = (z^2 / 2n) / (1 + z^2/n)

    so the lower bound is exactly 0 and the upper bound is exactly z^2 / (n + z^2).
    For n = 1, z = 1.6448536269514722:  z^2 = 2.705543454095404
        upper = 2.705543454095413 / 3.705543454095413 = 0.7301340512159458
    """
    z = 1.6448536269514722
    low, high = wilson_interval(0, 1, z=z)
    assert low == pytest.approx(0.0, abs=1e-12)
    assert high == pytest.approx((z * z) / (1 + z * z), abs=1e-12)
    assert high == pytest.approx(0.7301340512159458, abs=1e-12)


def test_wilson_interval_all_hits_hand_derived():
    """With p-hat = 1 the bounds collapse to n/(n + z^2) and 1.

    For n = 4:  4 / (4 + 2.705543454095413) = 4 / 6.705543454095413 = 0.5965213747972954
    """
    z = 1.6448536269514722
    low, high = wilson_interval(4, 4, z=z)
    assert low == pytest.approx(4 / (4 + z * z), abs=1e-12)
    assert low == pytest.approx(0.5965213747972954, abs=1e-12)
    assert high == pytest.approx(1.0, abs=1e-12)


def test_wilson_interval_matches_the_formula_written_out_independently():
    z = 1.6448536269514722
    for hits, n in [(1, 3), (5, 9), (12, 40), (0, 7), (7, 7)]:
        phat = hits / n
        denominator = 1 + z * z / n
        centre = (phat + z * z / (2 * n)) / denominator
        margin = (z / denominator) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
        low, high = wilson_interval(hits, n, z=z)
        assert low == pytest.approx(max(0.0, centre - margin))
        assert high == pytest.approx(min(1.0, centre + margin))


def test_wilson_interval_narrows_as_the_sample_grows():
    """The point of showing intervals: small buckets must look uncertain."""
    small = wilson_interval(3, 4)
    large = wilson_interval(75, 100)
    assert (small[1] - small[0]) > (large[1] - large[0])


def test_wilson_interval_rejects_impossible_input():
    with pytest.raises(ValueError):
        wilson_interval(0, 0)
    with pytest.raises(ValueError):
        wilson_interval(5, 4)


# --------------------------------------------------------------------------------------
# Rolling
# --------------------------------------------------------------------------------------

def test_rolling_brier_is_cumulative_and_hand_computed():
    """Resolved in date order, the running mean is:

        after 1:  0.04                  / 1 = 0.04
        after 2: (0.04 + 0.09)          / 2 = 0.065
        after 3: (0.04 + 0.09 + 0.36)   / 3 = 0.16333333...
    """
    predictions = [
        make(80, True, resolved_at="2026-06-02"),
        make(30, False, resolved_at="2026-06-03"),
        make(60, False, resolved_at="2026-06-04"),
    ]
    points = rolling_brier(predictions)
    assert [p.index for p in points] == [1, 2, 3]
    assert points[0].brier_to_date == pytest.approx(0.04)
    assert points[1].brier_to_date == pytest.approx(0.065)
    assert points[2].brier_to_date == pytest.approx(0.49 / 3)


def test_rolling_brier_orders_by_resolution_date_not_file_order():
    late = make(60, False, resolved_at="2026-06-04")
    early = make(80, True, resolved_at="2026-06-02")
    points = rolling_brier([late, early])
    assert [p.date for p in points] == ["2026-06-02", "2026-06-04"]
    assert points[0].brier_to_date == pytest.approx(0.04)


def test_rolling_brier_is_empty_when_nothing_resolved():
    assert rolling_brier([make(70), make(20)]) == []


# --------------------------------------------------------------------------------------
# Standing
# --------------------------------------------------------------------------------------

def test_standing_counts_open_predictions_and_reports_both_hits_and_misses():
    predictions = [make(80, True), make(30, False), make(60, False), make(90), make(10)]
    result = standing(predictions)
    assert result.total == 5
    assert result.resolved == 3
    assert result.open == 2
    assert result.hits == 1
    assert result.misses == 2
    assert result.brier == pytest.approx(0.49 / 3)
    assert result.skill == pytest.approx(0.3466666666666667)


def test_standing_with_nothing_resolved_reports_none_not_zero():
    result = standing([make(80), make(30)])
    assert result.resolved == 0
    assert result.open == 2
    assert result.brier is None
    assert result.skill is None


def test_there_is_no_percentage_correct_metric():
    """Guard against someone helpfully adding the wrong headline metric later."""
    exported = dir(scoring)
    for forbidden in ("percent_correct", "percentage_correct", "accuracy", "hit_rate"):
        assert forbidden not in exported


# --------------------------------------------------------------------------------------
# Example records must never reach the maths
# --------------------------------------------------------------------------------------

def test_example_records_are_excluded_from_the_brier_score():
    """Seeded placeholders carry invented outcomes. They must not move the headline number."""
    real = [make(80, True), make(30, False), make(60, False)]
    with_examples = [*real, make(5, True, example=True), make(95, False, example=True)]
    assert brier_score(with_examples) == pytest.approx(0.49 / 3)
    assert brier_score(with_examples) == brier_score(real)


def test_a_record_set_that_is_only_examples_scores_none_not_a_number():
    """A fresh deployment has no track record. It must say so rather than show a flattering score."""
    only_examples = [make(75, True, example=True), make(65, False, example=True)]
    assert brier_score(only_examples) is None
    assert skill_score(brier_score(only_examples)) is None
    assert rolling_brier(only_examples) == []
    assert all(b.empty for b in calibration(only_examples))


def test_example_records_are_excluded_from_calibration():
    buckets = calibration([make(75, True), make(75, True, example=True), make(75, False, example=True)])
    assert buckets[7].count == 1
    assert buckets[7].hits == 1


def test_example_records_are_excluded_from_the_rolling_series():
    points = rolling_brier([
        make(80, True, resolved_at="2026-06-02"),
        make(10, False, resolved_at="2026-06-03", example=True),
    ])
    assert [p.brier_to_date for p in points] == pytest.approx([0.04])


def test_standing_counts_examples_separately_and_excludes_them_everywhere_else():
    predictions = [make(80, True), make(90), make(50, True, example=True), make(50, False, example=True)]
    result = standing(predictions)
    assert result.examples == 2
    assert result.total == 2      # real records only
    assert result.resolved == 1
    assert result.open == 1
    assert result.hits == 1
    assert result.misses == 0
    assert result.brier == pytest.approx(0.04)


def test_every_scoring_entry_point_goes_through_the_example_filter():
    """Guard against a future function that reads the raw list and reintroduces the bug."""
    import inspect

    source = inspect.getsource(scoring)
    for function in ("def brier_score", "def calibration", "def rolling_brier", "def standing"):
        body = source.split(function, 1)[1].split("\ndef ", 1)[0]
        assert "scored(" in body, f"{function} does not filter example records"
