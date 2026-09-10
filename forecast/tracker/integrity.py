"""Verify prediction records against git history.

Two questions, answered from git rather than from the files themselves:

1. Does each record's `created_at` match the date of the commit that first added it?
2. Have any of the locked fields changed in any later commit?

(2) is the stronger check and the one that matters. A forecaster who quietly lowered a
probability, softened a claim, or rewrote their reasoning after seeing the outcome would leave
the current file looking perfectly consistent -- only the history shows it.

Honest limit, stated plainly because the whole project is about not overclaiming: git author
dates are written by whoever makes the commit and can be backdated locally. This check proves
the record is internally consistent with its own history; it does not prove that history was
not manufactured. The independent evidence is the public push timestamps held by the hosting
platform, which the repository owner cannot rewrite. See report.caveat.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .model import LOCKED_FIELDS, Prediction

CAVEAT = (
    "Git author dates are written by the committer and can be backdated on a local machine. "
    "These checks prove each record is consistent with its own commit history; independent "
    "proof of timing is the host's public push log, which the repository owner cannot rewrite."
)


class GitUnavailable(RuntimeError):
    """The verification could not be run at all -- not the same as it failing."""


@dataclass
class FileVerdict:
    prediction_id: str
    path: str
    tracked: bool
    first_commit: str | None = None
    first_commit_date: _dt.date | None = None
    created_at: _dt.date | None = None
    revisions: int = 0
    problems: list[str] = field(default_factory=list)
    dirty: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class Report:
    verdicts: list[FileVerdict]
    caveat: str = CAVEAT
    checked_at: str = ""

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.verdicts)

    @property
    def failures(self) -> list[FileVerdict]:
        return [v for v in self.verdicts if not v.ok]

    @property
    def summary(self) -> str:
        total = len(self.verdicts)
        bad = len(self.failures)
        if total == 0:
            return "No prediction records to verify."
        if bad == 0:
            return (
                f"All {total} records match their first commit date, and no locked field has "
                "changed since the commit that created it."
            )
        return f"{bad} of {total} records failed verification."


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on host
        raise GitUnavailable("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise GitUnavailable(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.strip() or 'no stderr'}"
        )
    return result.stdout


def _rel(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def _commits_touching(repo: Path, relpath: str) -> list[tuple[str, _dt.date]]:
    """(sha, author date) for every commit touching the file, newest first."""
    out = _git(repo, "log", "--format=%H%x1f%aI", "--", relpath)
    commits: list[tuple[str, _dt.date]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, iso = line.partition("\x1f")
        commits.append((sha, _dt.datetime.fromisoformat(iso).date()))
    return commits


def _blob_at(repo: Path, sha: str, relpath: str) -> dict | None:
    try:
        raw = _git(repo, "show", f"{sha}:{relpath}")
    except GitUnavailable:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def verify_prediction(repo: Path, prediction: Prediction) -> FileVerdict:
    relpath = _rel(repo, prediction.path)
    verdict = FileVerdict(
        prediction_id=prediction.id,
        path=relpath,
        tracked=False,
        created_at=prediction.created_at,
    )

    listed = _git(repo, "ls-files", "--", relpath).strip()
    if not listed:
        verdict.problems.append(
            "not committed to git, so there is no history to check it against. "
            "An uncommitted prediction carries no evidence of when it was written."
        )
        return verdict
    verdict.tracked = True

    if _git(repo, "diff", "--name-only", "--", relpath).strip():
        verdict.dirty = True
        verdict.problems.append(
            "has uncommitted local modifications. The published record and the working copy differ."
        )

    commits = _commits_touching(repo, relpath)
    verdict.revisions = len(commits)
    if not commits:
        verdict.problems.append("is tracked but has no commit history, which should be impossible.")
        return verdict

    first_sha, first_date = commits[-1]
    verdict.first_commit = first_sha
    verdict.first_commit_date = first_date

    if first_date != prediction.created_at:
        verdict.problems.append(
            f"declares created_at {prediction.created_at.isoformat()} but its first commit "
            f"({first_sha[:10]}) is dated {first_date.isoformat()}."
        )

    # Every historical revision must agree with the current file on the locked fields.
    current = {f: getattr(prediction, f) for f in LOCKED_FIELDS}
    current["created_at"] = prediction.created_at.isoformat()
    current["resolves_on"] = prediction.resolves_on.isoformat()

    for sha, _date in commits:
        historical = _blob_at(repo, sha, relpath)
        if historical is None:
            verdict.problems.append(f"revision {sha[:10]} could not be read or parsed as JSON.")
            continue
        for field_name in LOCKED_FIELDS:
            was = historical.get(field_name)
            now = current[field_name]
            if isinstance(now, str) and isinstance(was, str):
                changed = was.strip() != now.strip()
            else:
                changed = was != now
            if changed:
                verdict.problems.append(
                    f"locked field '{field_name}' was changed after creation: revision "
                    f"{sha[:10]} had {was!r}, the current file has {now!r}."
                )
    return verdict


def verify_all(repo: Path, predictions: list[Prediction]) -> Report:
    inside = _git(repo, "rev-parse", "--is-inside-work-tree").strip()
    if inside != "true":
        raise GitUnavailable(f"{repo} is not inside a git work tree")
    verdicts = [verify_prediction(repo, p) for p in predictions]
    return Report(
        verdicts=verdicts,
        checked_at=_dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
    )
