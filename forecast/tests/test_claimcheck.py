"""The vague-claim gate. Better to reject a good claim than accept an arguable one."""

from __future__ import annotations

import pytest
from tracker.claimcheck import check_claim, check_reasoning, check_resolution_source

GOOD_CLAIM = "PLACEHOLDER INDEX (example, not real) prints at or above 2.0% year on year in the stated release."


def test_a_precise_claim_passes():
    assert check_claim(GOOD_CLAIM) == []


@pytest.mark.parametrize(
    "claim,expected_fragment",
    [
        ("Inflation goes up", "too short"),
        ("PLACEHOLDER INDEX (example, not real) rises in the stated release for March.", "no number"),
        ("PLACEHOLDER INDEX (example, not real) prints 2.0% in the stated release for March.", "no direction"),
        ("PLACEHOLDER INDEX (example) will probably be at or above 2.0% in the March release.", "hedging"),
        ("PLACEHOLDER INDEX (example) shows a significant move above 2.0% in the March release.", "hedging"),
    ],
)
def test_vague_claims_are_refused_with_a_reason(claim, expected_fragment):
    problems = check_claim(claim)
    assert problems, f"expected {claim!r} to be refused"
    assert any(expected_fragment in p for p in problems)


def test_all_comparator_forms_are_accepted():
    for direction in ["at or above", "below", "at least", ">=", "≥", "or higher"]:
        claim = f"PLACEHOLDER INDEX (example, not real) prints {direction} 2.0% in the stated March release."
        assert check_claim(claim) == [], f"{direction} should be accepted"


def test_hedge_detection_is_word_bounded():
    """'about' must not fire inside 'roundabout'; the check should not be superstitious."""
    claim = "PLACEHOLDER ROUNDABOUT INDEX (example) prints at or above 2.0% in the stated March release."
    assert check_claim(claim) == []


def test_resolution_source_needs_a_period_and_a_kind():
    assert check_resolution_source("Placeholder statistical release, March 2026") == []
    assert any("period" in p for p in check_resolution_source("Placeholder statistical release"))
    assert any("kind" in p for p in check_resolution_source("Placeholder body, March 2026"))
    assert any("too short" in p for p in check_resolution_source("March"))


def test_reasoning_must_be_two_to_five_sentences():
    assert check_reasoning("Placeholder rationale one. Placeholder rationale two.") == []
    assert any("fewer than 2" in p for p in check_reasoning("One long placeholder sentence with no second one"))
    six = " ".join(f"Placeholder rationale sentence {n}." for n in range(6))
    assert any("Keep it to 5" in p for p in check_reasoning(six))
