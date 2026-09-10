"""Builders for test fixtures."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from tracker.model import Prediction

_SEQ = [0]


def make(
    probability: int,
    outcome: bool | None = None,
    *,
    pid: str | None = None,
    created_at: str = "2026-01-01",
    resolves_on: str = "2026-06-01",
    resolved_at: str | None = "2026-06-02",
    claim: str = "PLACEHOLDER INDEX (example) prints at or above 2.0% in the stated release.",
    reasoning: str = "Placeholder rationale sentence one. Placeholder rationale sentence two.",
) -> Prediction:
    _SEQ[0] += 1
    identifier = pid or f"P-{_SEQ[0]:04d}"
    resolved = outcome is not None
    return Prediction(
        id=identifier,
        created_at=_dt.date.fromisoformat(created_at),
        resolves_on=_dt.date.fromisoformat(resolves_on),
        claim=claim,
        probability=probability,
        reasoning=reasoning,
        resolution_source="Placeholder statistical release, March 2026",
        outcome=outcome,
        resolved_at=_dt.date.fromisoformat(resolved_at) if resolved and resolved_at else None,
        resolution_note="Placeholder resolution note." if resolved else None,
        example=True,
        path=Path(f"predictions/{identifier}.json"),
    )
