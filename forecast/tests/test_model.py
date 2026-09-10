"""Record parsing must fail loudly and specifically. No silent defaults."""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from pathlib import Path

import pytest
from helpers import make
from tracker.model import RecordError, load_all, load_file, next_id, parse, to_json

VALID = {
    "id": "P-0007",
    "created_at": "2026-01-15",
    "resolves_on": "2026-04-01",
    "claim": "PLACEHOLDER INDEX (example, not real) prints at or above 2.0% in the stated release.",
    "probability": 65,
    "reasoning": "Placeholder rationale sentence one. Placeholder rationale sentence two.",
    "resolution_source": "Placeholder statistical release, March 2026",
    "outcome": None,
    "resolved_at": None,
    "resolution_note": None,
}


def _parse(**overrides):
    data = {**VALID, **overrides}
    for key in [k for k, v in overrides.items() if v is ...]:
        del data[key]
    return parse(data, Path("predictions/P-0007.json"))


def test_parses_a_valid_open_record():
    prediction = _parse()
    assert prediction.id == "P-0007"
    assert prediction.created_at == _dt.date(2026, 1, 15)
    assert prediction.probability == 65
    assert prediction.p == pytest.approx(0.65)
    assert prediction.resolved is False
    assert prediction.sequence == 7


def test_parses_a_valid_resolved_record():
    prediction = _parse(outcome=True, resolved_at="2026-04-02", resolution_note="Placeholder note here.")
    assert prediction.resolved is True
    assert prediction.outcome is True
    assert prediction.resolved_at == _dt.date(2026, 4, 2)


@pytest.mark.parametrize("field", ["id", "created_at", "resolves_on", "claim", "probability", "reasoning", "resolution_source"])
def test_missing_required_field_names_the_field(field):
    with pytest.raises(RecordError, match=field):
        _parse(**{field: ...})


def test_unknown_field_is_rejected_rather_than_ignored():
    """A typo'd field name must not silently vanish."""
    with pytest.raises(RecordError, match="probabilty"):
        _parse(probabilty=65)


@pytest.mark.parametrize("bad", [101, -1])
def test_probability_out_of_range(bad):
    with pytest.raises(RecordError, match="0-100"):
        _parse(probability=bad)


@pytest.mark.parametrize("bad", ["65", 65.5, True, None])
def test_probability_must_be_a_plain_integer(bad):
    with pytest.raises(RecordError, match="probability"):
        _parse(probability=bad)


def test_malformed_date_is_rejected():
    with pytest.raises(RecordError, match="not a valid ISO date"):
        _parse(created_at="15/01/2026")


def test_resolution_before_creation_is_rejected():
    with pytest.raises(RecordError, match="before"):
        _parse(resolves_on="2025-12-01")


def test_outcome_must_be_boolean_or_null():
    with pytest.raises(RecordError, match="outcome"):
        _parse(outcome="true")


def test_resolution_fields_without_an_outcome_are_rejected():
    """Guards against a half-written resolution being read as an open prediction."""
    with pytest.raises(RecordError, match="cannot carry a resolution"):
        _parse(resolved_at="2026-04-02")


def test_outcome_without_a_resolution_date_is_rejected():
    with pytest.raises(RecordError, match="resolved_at"):
        _parse(outcome=False, resolved_at=None, resolution_note="Placeholder note here.")


def test_outcome_without_a_note_is_rejected():
    with pytest.raises(RecordError, match="resolution_note"):
        _parse(outcome=False, resolved_at="2026-04-02", resolution_note=None)


def test_short_claim_is_rejected():
    with pytest.raises(RecordError, match="claim"):
        _parse(claim="CPI up")


def test_bad_id_shape_is_rejected():
    with pytest.raises(RecordError, match="id"):
        _parse(id="7")


def test_round_trip_through_json_is_stable(tmp_path):
    path = tmp_path / "P-0007.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    first = load_file(path)
    path.write_text(to_json(first), encoding="utf-8")
    second = load_file(path)
    assert to_json(first) == to_json(second)
    assert first.claim == second.claim


def test_filename_must_match_id(tmp_path):
    path = tmp_path / "P-0009.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    with pytest.raises(RecordError, match="filename does not match id"):
        load_file(path)


def test_invalid_json_names_the_file_and_position(tmp_path):
    path = tmp_path / "P-0007.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(RecordError, match="not valid JSON"):
        load_file(path)


def test_load_all_sorts_newest_first(tmp_path):
    for index, created in enumerate(["2026-01-01", "2026-03-01", "2026-02-01"], start=1):
        record = {**VALID, "id": f"P-{index:04d}", "created_at": created, "resolves_on": "2026-12-01"}
        (tmp_path / f"P-{index:04d}.json").write_text(json.dumps(record), encoding="utf-8")
    ids = [p.id for p in load_all(tmp_path)]
    assert ids == ["P-0002", "P-0003", "P-0001"]


def test_load_all_on_a_missing_directory_raises():
    with pytest.raises(RecordError, match="does not exist"):
        load_all(Path("/nonexistent/predictions"))


def test_next_id_increments_and_pads():
    assert next_id([]) == "P-0001"
    assert next_id([make(50, pid="P-0001"), make(50, pid="P-0009")]) == "P-0010"


def test_prediction_is_frozen():
    """The record objects are immutable in memory too -- no accidental in-place edits."""
    prediction = _parse()
    with pytest.raises(dataclasses.FrozenInstanceError):
        prediction.probability = 90  # type: ignore[misc]


def test_is_due():
    prediction = _parse(resolves_on="2026-04-01")
    assert prediction.is_due(_dt.date(2026, 4, 1)) is True
    assert prediction.is_due(_dt.date(2026, 3, 31)) is False
    resolved = _parse(resolves_on="2026-04-01", outcome=True, resolved_at="2026-04-02", resolution_note="Placeholder note.")
    assert resolved.is_due(_dt.date(2026, 5, 1)) is False


def test_an_empty_prediction_directory_loads_as_an_empty_record_set(tmp_path):
    """Deleting the last record must not break the build.

    Git does not track empty directories, so removing the final prediction file also removes
    predictions/ unless something keeps it present. A tracker with nothing in it yet is a
    legitimate state; a *missing* directory usually means the command ran from the wrong
    place, which is why that still raises.
    """
    empty = tmp_path / "predictions"
    empty.mkdir()
    assert load_all(empty) == []


def test_non_json_files_in_the_directory_are_ignored(tmp_path):
    """.gitkeep and similar must not be parsed as records."""
    directory = tmp_path / "predictions"
    directory.mkdir()
    (directory / ".gitkeep").write_text("# placeholder\n", encoding="utf-8")
    (directory / "README.md").write_text("notes\n", encoding="utf-8")
    assert load_all(directory) == []
