"""Shared plumbing for the CLI scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NoReturn

BIN_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BIN_DIR.parent
PREDICTIONS_DIR = PROJECT_DIR / "predictions"
sys.path.insert(0, str(PROJECT_DIR))


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=PROJECT_DIR, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        die("not inside a git repository -- the record has no tamper-evidence without one")
    return Path(result.stdout.strip())


def die(message: str, code: int = 1) -> NoReturn:  # type: ignore[name-defined]
    print(f"\nerror: {message}", file=sys.stderr)
    raise SystemExit(code)


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd or repo_root(), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        die(f"git {' '.join(args)} failed: {result.stderr.strip() or 'no stderr'}")
    return result.stdout


def ask(prompt: str, *, multiline: bool = False) -> str:
    """Read a value from the terminal. Blank input is re-prompted, never defaulted."""
    if multiline:
        print(f"{prompt}\n(finish with a blank line)")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not line.strip() and lines:
                break
            if line.strip():
                lines.append(line.strip())
        return " ".join(lines).strip()
    while True:
        try:
            value = input(f"{prompt} ").strip()
        except EOFError:
            die("input ended before the record was complete; nothing was written")
        if value:
            return value
        print("  (required)")


def report_problems(field: str, problems: list[str]) -> None:
    print(f"\n  {field} rejected:")
    for problem in problems:
        print(f"    - {problem}")


def rebuild_and_commit_site(root: Path) -> None:
    """Regenerate docs/ and commit it if it changed.

    Run after every record change so the published page can never drift from the records it
    claims to describe. A separate commit, so the prediction's own history stays readable.
    """
    from tracker.integrity import GitUnavailable, verify_all
    from tracker.model import load_all
    from tracker.render import write_site

    predictions = load_all(PREDICTIONS_DIR)
    report = None
    integrity_error = None
    try:
        report = verify_all(root, predictions)
    except GitUnavailable as exc:
        integrity_error = str(exc)

    write_site(predictions, report, root / "docs", integrity_error)
    if git("status", "--porcelain", "--", "docs").strip():
        git("add", "--", "docs")
        git("commit", "-m", "rebuild dashboard")
        print("dashboard rebuilt and committed")
    else:
        print("dashboard already up to date")
