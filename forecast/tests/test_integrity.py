"""Verification against real git history, including a simulated after-the-fact edit.

These build throwaway repositories rather than mocking git, because the thing being tested is
precisely whether the code reads git correctly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from tracker.integrity import GitUnavailable, verify_all
from tracker.model import load_all

RECORD = {
    "id": "P-0001",
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


def _run(repo: Path, *args: str, when: str | None = None) -> None:
    env = None
    if when:
        stamp = f"{when}T12:00:00+00:00"
        env = {
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(repo),
        }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _run(tmp_path, "init", "-q", "-b", "main")
    _run(tmp_path, "config", "user.email", "test@example.invalid")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / "predictions").mkdir()
    return tmp_path


def _write(repo: Path, record: dict) -> Path:
    path = repo / "predictions" / f"{record['id']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _commit(repo: Path, message: str, when: str) -> None:
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", message, when=when)


def _verify(repo: Path):
    return verify_all(repo, load_all(repo / "predictions"))


def test_a_record_committed_on_its_stated_date_verifies_clean(repo):
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")
    report = _verify(repo)
    assert report.ok
    assert report.verdicts[0].first_commit_date.isoformat() == "2026-01-15"
    assert "no locked field has changed" in report.summary


def test_created_at_not_matching_the_first_commit_is_flagged(repo):
    """The record claims it was written weeks before the commit that introduced it."""
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-02-20")
    report = _verify(repo)
    assert not report.ok
    problem = report.verdicts[0].problems[0]
    assert "created_at 2026-01-15" in problem
    assert "2026-02-20" in problem


def test_editing_the_probability_after_the_fact_is_caught(repo):
    """The scenario the whole project exists to make impossible to hide."""
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")

    _write(repo, {**RECORD, "probability": 95})
    _commit(repo, "innocuous looking follow-up", when="2026-04-05")

    report = _verify(repo)
    assert not report.ok
    joined = " ".join(report.verdicts[0].problems)
    assert "locked field 'probability' was changed" in joined
    assert "65" in joined and "95" in joined


def test_editing_the_claim_after_the_fact_is_caught(repo):
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")
    softened = {**RECORD, "claim": "PLACEHOLDER INDEX (example, not real) prints at or above 1.0% in the stated release."}
    _write(repo, softened)
    _commit(repo, "tweak", when="2026-04-05")
    report = _verify(repo)
    assert any("locked field 'claim' was changed" in p for p in report.verdicts[0].problems)


def test_resolving_a_prediction_is_not_treated_as_tampering(repo):
    """Writing outcome/resolved_at/resolution_note is the one legitimate later edit."""
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")

    resolved = {
        **RECORD,
        "outcome": False,
        "resolved_at": "2026-04-02",
        "resolution_note": "Placeholder resolution note for the example record.",
    }
    _write(repo, resolved)
    _commit(repo, "resolve P-0001", when="2026-04-02")

    report = _verify(repo)
    assert report.ok, report.verdicts[0].problems
    assert report.verdicts[0].revisions == 2


def test_an_uncommitted_prediction_is_flagged_not_trusted(repo):
    _write(repo, RECORD)
    report = _verify(repo)
    assert not report.ok
    assert "not committed to git" in report.verdicts[0].problems[0]
    assert report.verdicts[0].tracked is False


def test_uncommitted_local_modifications_are_flagged(repo):
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")
    _write(repo, {**RECORD, "probability": 95})
    report = _verify(repo)
    assert report.verdicts[0].dirty is True
    assert any("uncommitted local modifications" in p for p in report.verdicts[0].problems)


def test_report_summary_counts_failures(repo):
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")
    second = {**RECORD, "id": "P-0002"}
    _write(repo, second)
    _commit(repo, "add P-0002", when="2026-03-03")  # deliberately wrong date
    report = _verify(repo)
    assert report.summary == "1 of 2 records failed verification."


def test_the_report_carries_the_honest_caveat(repo):
    _write(repo, RECORD)
    _commit(repo, "add P-0001", when="2026-01-15")
    report = _verify(repo)
    assert "backdated" in report.caveat
    assert "push log" in report.caveat


def test_verifying_outside_a_git_work_tree_raises_rather_than_passing(tmp_path):
    """A missing git must never be reported as a clean bill of health."""
    (tmp_path / "predictions").mkdir()
    with pytest.raises(GitUnavailable):
        verify_all(tmp_path, [])
