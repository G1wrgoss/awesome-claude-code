"""Prediction records: schema, parsing, validation.

Records are plain JSON files, one per prediction, committed to git. There is no database and
no update path for the locked fields -- see integrity.py for how that is enforced against
git history rather than merely asserted here.

Every failure raises RecordError naming the file and the field. Nothing defaults silently.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Fields that must never change once the record's first commit lands. integrity.py checks
# every historical revision of every file against this list.
LOCKED_FIELDS = (
    "id",
    "created_at",
    "resolves_on",
    "claim",
    "probability",
    "reasoning",
    "resolution_source",
)

# Fields written only at resolution time.
RESOLUTION_FIELDS = ("outcome", "resolved_at", "resolution_note")

OPTIONAL_FIELDS = ("example",)

ALL_FIELDS = LOCKED_FIELDS + RESOLUTION_FIELDS + OPTIONAL_FIELDS

ID_PATTERN = re.compile(r"^P-\d{4,}$")


class RecordError(ValueError):
    """A prediction file is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Prediction:
    id: str
    created_at: _dt.date
    resolves_on: _dt.date
    claim: str
    probability: int  # integer 0-100
    reasoning: str
    resolution_source: str
    outcome: bool | None
    resolved_at: _dt.date | None
    resolution_note: str | None
    example: bool
    path: Path

    @property
    def resolved(self) -> bool:
        return self.outcome is not None

    @property
    def p(self) -> float:
        """Stated probability as a fraction in [0, 1]."""
        return self.probability / 100.0

    @property
    def sequence(self) -> int:
        return int(self.id.split("-", 1)[1])

    def is_due(self, today: _dt.date) -> bool:
        """Past its resolution date and still open."""
        return not self.resolved and self.resolves_on <= today


def _fail(path: Path, message: str) -> None:
    raise RecordError(f"{path}: {message}")


def _require_date(path: Path, field: str, raw: Any) -> _dt.date:
    if not isinstance(raw, str):
        _fail(path, f"field {field!r} must be an ISO date string (YYYY-MM-DD), got {type(raw).__name__}")
    try:
        return _dt.date.fromisoformat(raw)
    except ValueError as exc:
        _fail(path, f"field {field!r} is not a valid ISO date: {raw!r} ({exc})")
    raise AssertionError("unreachable")


def _require_text(path: Path, field: str, raw: Any, min_len: int) -> str:
    if not isinstance(raw, str):
        _fail(path, f"field {field!r} must be a string, got {type(raw).__name__}")
    text = raw.strip()
    if len(text) < min_len:
        _fail(path, f"field {field!r} is too short to be meaningful ({len(text)} chars, need >= {min_len})")
    return text


def parse(data: dict[str, Any], path: Path) -> Prediction:
    """Turn a decoded JSON object into a Prediction, or raise RecordError."""
    if not isinstance(data, dict):
        _fail(path, f"top level must be a JSON object, got {type(data).__name__}")

    unknown = sorted(set(data) - set(ALL_FIELDS))
    if unknown:
        _fail(path, f"unknown field(s): {', '.join(unknown)}. Allowed: {', '.join(ALL_FIELDS)}")

    for field in LOCKED_FIELDS:
        if field not in data:
            _fail(path, f"required field {field!r} is missing")

    pid = data["id"]
    if not isinstance(pid, str) or not ID_PATTERN.match(pid):
        _fail(path, f"field 'id' must look like 'P-0001', got {pid!r}")

    created_at = _require_date(path, "created_at", data["created_at"])
    resolves_on = _require_date(path, "resolves_on", data["resolves_on"])
    if resolves_on < created_at:
        _fail(path, f"'resolves_on' ({resolves_on}) is before 'created_at' ({created_at})")

    claim = _require_text(path, "claim", data["claim"], min_len=40)
    reasoning = _require_text(path, "reasoning", data["reasoning"], min_len=40)
    resolution_source = _require_text(path, "resolution_source", data["resolution_source"], min_len=10)

    probability = data["probability"]
    if isinstance(probability, bool) or not isinstance(probability, int):
        _fail(path, f"field 'probability' must be an integer 0-100, got {probability!r}")
    if not 0 <= probability <= 100:
        _fail(path, f"field 'probability' must be within 0-100, got {probability}")

    outcome = data.get("outcome")
    if outcome is not None and not isinstance(outcome, bool):
        _fail(path, f"field 'outcome' must be true, false, or null, got {outcome!r}")

    resolved_at_raw = data.get("resolved_at")
    resolution_note_raw = data.get("resolution_note")

    if outcome is None:
        for field, value in (("resolved_at", resolved_at_raw), ("resolution_note", resolution_note_raw)):
            if value is not None:
                _fail(path, f"field {field!r} is set but 'outcome' is null -- an unresolved prediction cannot carry a resolution")
        resolved_at = None
        resolution_note = None
    else:
        if resolved_at_raw is None:
            _fail(path, "'outcome' is set but 'resolved_at' is missing")
        resolved_at = _require_date(path, "resolved_at", resolved_at_raw)
        if resolved_at < created_at:
            _fail(path, f"'resolved_at' ({resolved_at}) is before 'created_at' ({created_at})")
        resolution_note = _require_text(path, "resolution_note", resolution_note_raw, min_len=10)

    example = data.get("example", False)
    if not isinstance(example, bool):
        _fail(path, f"field 'example' must be a boolean, got {example!r}")

    return Prediction(
        id=pid,
        created_at=created_at,
        resolves_on=resolves_on,
        claim=claim,
        probability=probability,
        reasoning=reasoning,
        resolution_source=resolution_source,
        outcome=outcome,
        resolved_at=resolved_at,
        resolution_note=resolution_note,
        example=example,
        path=path,
    )


def load_file(path: Path) -> Prediction:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecordError(f"{path}: cannot be read ({exc})") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RecordError(f"{path}: is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})") from exc
    prediction = parse(data, path)
    expected_name = f"{prediction.id}.json"
    if path.name != expected_name:
        _fail(path, f"filename does not match id -- expected {expected_name}")
    return prediction


def load_all(directory: Path) -> list[Prediction]:
    """Load every prediction file, newest first. Raises on the first bad record."""
    if not directory.is_dir():
        raise RecordError(f"{directory}: prediction directory does not exist")
    predictions = [load_file(p) for p in sorted(directory.glob("*.json"))]
    seen: dict[str, Path] = {}
    for prediction in predictions:
        if prediction.id in seen:
            raise RecordError(f"{prediction.path}: duplicate id {prediction.id} (also in {seen[prediction.id]})")
        seen[prediction.id] = prediction.path
    predictions.sort(key=lambda p: (p.created_at, p.sequence), reverse=True)
    return predictions


def to_json(prediction: Prediction) -> str:
    """Serialise in a fixed key order so diffs stay legible and stable."""
    payload: dict[str, Any] = {
        "id": prediction.id,
        "created_at": prediction.created_at.isoformat(),
        "resolves_on": prediction.resolves_on.isoformat(),
        "claim": prediction.claim,
        "probability": prediction.probability,
        "reasoning": prediction.reasoning,
        "resolution_source": prediction.resolution_source,
        "outcome": prediction.outcome,
        "resolved_at": prediction.resolved_at.isoformat() if prediction.resolved_at else None,
        "resolution_note": prediction.resolution_note,
    }
    if prediction.example:
        payload["example"] = True
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def next_id(existing: list[Prediction]) -> str:
    highest = max((p.sequence for p in existing), default=0)
    return f"P-{highest + 1:04d}"
