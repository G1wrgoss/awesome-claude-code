"""Gatekeeping for claim text.

A prediction is only worth scoring if it cannot be argued about after the fact. These checks
are deliberately blunt: they reject anything that does not name an indicator, state a numeric
threshold with a direction, and point at a specific release. They will occasionally reject a
claim that was actually fine. That is the correct direction to err -- a vague claim that slips
through poisons the track record permanently, whereas a rejected claim costs thirty seconds.
"""

from __future__ import annotations

import re

# Words that make a claim unfalsifiable. If the forecaster wants to hedge, that is what the
# probability field is for -- the claim itself must be binary.
HEDGE_WORDS = (
    "probably", "likely", "unlikely", "possibly", "maybe", "might", "could",
    "roughly", "around", "approximately", "about", "some", "several", "significant",
    "substantial", "meaningful", "strong", "weak", "improve", "worsen", "better",
    "worse", "high", "low", "soon", "near-term", "moderate",
)

# A threshold needs a direction. Without one, "CPI 2.5%" does not say which side wins.
DIRECTION_TERMS = (
    "at or above", "at or below", "above", "below", "at least", "at most",
    "greater than", "less than", "exceed", "exceeds", "no higher than", "no lower than",
    "equal to or", "or higher", "or lower", "or more", "or fewer", "or less",
    ">=", "<=", ">", "<", "≥", "≤",
)

# The resolution source must name a specific, dated publication.
SOURCE_PERIOD = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|q[1-4]\b|\b20\d{2}\b|\bh[12]\b)",
    re.IGNORECASE,
)
SOURCE_KIND = re.compile(
    r"(release|estimate|report|print|publication|bulletin|statistic|index|survey|decision|announcement|data)",
    re.IGNORECASE,
)

NUMBER = re.compile(r"\d")

# Template text that a forecaster meant to overwrite and did not. These pass every other check
# -- a filled-in example carries a real number and a real direction -- so without an explicit
# refusal a pasted template commits cleanly into the permanent record.
PLACEHOLDER_MARKERS = (
    "replace", "todo", "fixme", "xxx", "lorem ipsum", "placeholder",
    "e.g.", "your indicator", "your claim", "your reasoning",
)


def _placeholder_problems(text: str, field: str) -> list[str]:
    lowered = text.lower()
    found = sorted({m for m in PLACEHOLDER_MARKERS if m in lowered})
    if not found:
        return []
    return [
        (
            f"looks like unfilled template text: contains {', '.join(repr(f) for f in found)}. "
            f"Write your own {field}. (If this really is a placeholder record, pass --example.)"
        )
    ]


def check_claim(claim: str, *, example: bool = False) -> list[str]:
    """Return a list of problems with the claim. Empty list means it passes."""
    problems: list[str] = []
    text = claim.strip()
    lowered = text.lower()

    if not example:
        problems.extend(_placeholder_problems(text, "claim"))

    if len(text) < 40:
        problems.append(
            f"too short ({len(text)} chars). A claim must name the indicator, the threshold "
            "and the release it resolves against; that does not fit in 40 characters."
        )

    if not NUMBER.search(text):
        problems.append(
            "contains no number. State the exact threshold, e.g. 'at or above 2.0%'."
        )

    if not any(term in lowered for term in DIRECTION_TERMS):
        problems.append(
            "states no direction. A threshold needs a side: use 'at or above', 'below', "
            "'at least', '>=', and so on, so there is no argument about a tie."
        )

    found_hedges = sorted({w for w in HEDGE_WORDS if re.search(rf"\b{re.escape(w)}\b", lowered)})
    if found_hedges:
        problems.append(
            f"contains hedging or subjective word(s): {', '.join(found_hedges)}. "
            "The claim must be binary -- put your uncertainty in the probability field instead."
        )

    return problems


def check_resolution_source(source: str, *, example: bool = False) -> list[str]:
    """Return a list of problems with the resolution source. Empty list means it passes."""
    problems: list[str] = []
    text = source.strip()

    if not example:
        problems.extend(_placeholder_problems(text, "resolution source"))

    if len(text) < 10:
        problems.append(
            f"too short ({len(text)} chars). Name the publication and its period, e.g. "
            "'Eurostat HICP flash estimate, March 2026'."
        )
    if not SOURCE_PERIOD.search(text):
        problems.append(
            "names no period. Include the month, quarter or year of the specific release "
            "that settles this, so a later revision cannot be substituted for it."
        )
    if not SOURCE_KIND.search(text):
        problems.append(
            "does not say what kind of publication this is (release, estimate, report, "
            "print, decision...). Be specific enough that a reader can go and look it up."
        )
    return problems


def check_reasoning(reasoning: str, *, example: bool = False) -> list[str]:
    """Reasoning must be 2-5 sentences of the forecaster's own rationale."""
    problems: list[str] = []
    text = reasoning.strip()

    if not example:
        problems.extend(_placeholder_problems(text, "reasoning"))
    if len(text) < 40:
        problems.append(f"too short ({len(text)} chars). Two to five sentences of actual rationale.")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) < 2:
        problems.append("fewer than 2 sentences. State why you hold this probability, not just what you think.")
    if len(sentences) > 5:
        problems.append(f"{len(sentences)} sentences. Keep it to 5 -- if it needs more, the claim is doing too much.")
    return problems
