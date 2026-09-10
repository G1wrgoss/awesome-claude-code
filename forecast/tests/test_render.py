"""Rendering tests.

These check the properties the project's credibility depends on: that misses are present and
formatted identically to hits, that open predictions are never dropped, that thin buckets are
labelled, and that an empty record cannot render as a flattering number.
"""

from __future__ import annotations

import datetime as _dt
import re

import pytest
from helpers import make
from tracker.integrity import FileVerdict, Report
from tracker.render import build_page, calibration_svg, calibration_table, fmt_score, rolling_svg
from tracker.scoring import calibration, rolling_brier


def clean_report(predictions) -> Report:
    """A passing report matching the given records, as verify_all always produces."""
    return Report(
        verdicts=[
            FileVerdict(prediction_id=p.id, path=str(p.path), tracked=True, revisions=1)
            for p in predictions
        ],
        checked_at="2026-09-10T00:00:00+00:00",
    )


_SENTINEL = object()


def page(predictions, report=_SENTINEL, error=None) -> str:
    if report is _SENTINEL:
        report = clean_report(predictions)
    return build_page(predictions, report, error, record_updated=_dt.datetime(2026, 9, 10, tzinfo=_dt.timezone.utc))


def test_a_miss_is_rendered_as_prominently_as_a_hit():
    """Same element, same structure -- the only difference is the word and the colour class."""
    html = page([make(80, True, pid="P-0001"), make(80, False, pid="P-0002")])
    assert html.count("class='entry-resolution'") == 2
    assert html.count('class="entry entry--resolved"') == 2
    assert "came true" in html and "did not come true" in html
    assert "mark--true" in html and "mark--false" in html


def test_open_predictions_are_always_shown():
    html = page([make(80, True), make(45), make(90)])
    assert html.count('class="entry ') == 3
    assert html.count("'mark mark--open'") == 2
    assert "2 open and 1 resolved" in html


def test_nothing_resolved_renders_an_em_dash_not_a_zero():
    """A blank record must not be displayable as a perfect Brier score."""
    html = page([make(80), make(20)])
    assert "—" in html
    assert "0.0000" not in html
    assert "No resolved predictions yet" in html


def test_baseline_is_always_shown_next_to_the_brier_score():
    html = page([make(80, True), make(30, False)])
    assert "0.2500" in html
    assert "always saying 50%" in html
    assert "Skill vs baseline" in html


def test_the_page_never_reports_a_percentage_correct():
    html = page([make(80, True), make(30, False), make(60, False)])
    lowered = html.lower()
    for phrase in ("percent correct", "percentage correct", "accuracy rate", "success rate", "win rate"):
        assert phrase not in lowered
    # It should say explicitly why that measure is absent.
    assert "does not report a percentage of predictions that" in html


def test_thin_buckets_are_labelled_in_both_chart_and_table():
    buckets = calibration([make(75, True), make(75, False)])
    svg = calibration_svg(buckets)
    table = calibration_table(buckets)
    assert "(thin)" in svg
    assert "thin — 2 resolved, not meaningful" in table


def test_a_well_populated_bucket_is_not_labelled_thin():
    buckets = calibration([make(75, True) for _ in range(6)])
    assert "(thin)" not in calibration_svg(buckets)


def test_empty_buckets_appear_in_the_table_rather_than_being_dropped():
    table = calibration_table(calibration([make(75, True)]))
    assert table.count("<tr") == 11  # 10 buckets plus the header row
    assert "no predictions in this range" in table


def test_claim_text_is_escaped():
    hostile = "PLACEHOLDER <script>alert('x')</script> prints at or above 2.0% in the March release."
    html = page([make(50, True, claim=hostile)])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_reasoning_is_present_but_behind_a_disclosure():
    html = page([make(50, True, reasoning="Placeholder rationale one. Placeholder rationale two.")])
    assert "<details" in html
    assert "Reasoning as written at the time" in html
    assert "Placeholder rationale one." in html


def test_example_records_are_flagged_on_the_page():
    html = page([make(50, True, example=True)])
    assert "example record" in html
    assert "placeholder text, not real forecasts" in html


def test_integrity_failure_is_surfaced_not_swallowed():
    bad = FileVerdict(
        prediction_id="P-0001", path="predictions/P-0001.json", tracked=True,
        problems=["locked field 'probability' was changed after creation"],
    )
    html = page([make(50, True, pid="P-0001")], report=Report(verdicts=[bad]))
    assert "integrity--bad" in html
    assert "locked field &#x27;probability&#x27; was changed" in html or "locked field 'probability' was changed" in html
    assert "1 of 1 records failed verification" in html


def test_unrunnable_verification_is_reported_as_unverified_not_as_ok():
    html = page([make(50, True)], report=None, error="git is not installed")
    assert "integrity--unknown" in html
    assert "Treat the record as unverified" in html
    assert "integrity integrity--ok" not in html


def test_the_honest_caveat_about_backdating_is_on_the_page():
    html = page([make(50, True)])
    assert "backdated" in html
    assert "push log" in html


def test_page_is_valid_standalone_html_with_no_external_requests():
    """No network dependency: the page must render identically offline in ten years."""
    html = page([make(80, True), make(45)])
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "<script" not in html
    for pattern in (r'src\s*=\s*["\']https?:', r'href\s*=\s*["\']https?:', r"@import", r"url\(http"):
        assert not re.search(pattern, html), f"external reference found: {pattern}"


def test_numerals_are_declared_tabular():
    html = page([make(80, True)])
    assert "tabular-nums" in html
    assert '"tnum" 1' in html


def test_reduced_motion_is_respected_and_focus_is_visible():
    html = page([make(80, True)])
    assert "prefers-reduced-motion" in html
    assert ":focus-visible" in html


def test_rolling_svg_handles_the_single_point_case():
    points = rolling_brier([make(80, True)])
    svg = rolling_svg(points)
    assert "<svg" in svg and "baseline 0.2500" in svg
    assert "polyline" not in svg  # one point is not a line


def test_rolling_svg_empty_state():
    assert "Nothing resolved yet" in rolling_svg([])


def test_calibration_svg_never_connects_the_buckets():
    """Bucket-to-bucket movement at these sample sizes is noise; a line would imply a trajectory.

    Checked at volume too, because the scribble this produces only appears once enough buckets
    are populated to zigzag.
    """
    thin = calibration([make(25, True), make(75, False)])
    assert "polyline" not in calibration_svg(thin)
    many = calibration([make(p, True) for p in range(5, 100, 3)] + [make(p, False) for p in range(7, 100, 3)])
    assert "polyline" not in calibration_svg(many)


def test_extreme_buckets_are_drawn_inside_the_plot_frame():
    """A bucket at 0% or 100% must not straddle the axis it sits on."""
    import re as _re

    buckets = calibration([make(0, False) for _ in range(6)] + [make(100, True) for _ in range(6)])
    svg = calibration_svg(buckets)
    frame = _re.search(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" fill="none"', svg)
    assert frame, "plot frame not found"
    fx, fy, fw, fh = (int(g) for g in frame.groups())
    circles = _re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg)
    assert circles
    for cx, cy, r in ((float(a), float(b), float(c)) for a, b, c in circles):
        assert cx - r >= fx and cx + r <= fx + fw, f"circle at {cx} breaches the frame horizontally"
        assert cy - r >= fy and cy + r <= fy + fh, f"circle at {cy} breaches the frame vertically"


def test_chart_has_a_text_alternative():
    buckets = calibration([make(75, True) for _ in range(5)])
    svg = calibration_svg(buckets)
    assert 'role="img"' in svg
    assert "<title" in svg and "<desc" in svg


@pytest.mark.parametrize("value,expected", [(None, "—"), (0.25, "0.2500"), (0.1633333, "0.1633")])
def test_fmt_score(value, expected):
    assert fmt_score(value) == expected


def test_the_page_is_reproducible_for_unchanged_records():
    """Two builds of the same records must be byte-identical.

    Otherwise the CI check for a stale dashboard can never pass, and every rebuild produces a
    diff that hides what actually changed.
    """
    predictions = [make(80, True), make(45)]
    report = clean_report(predictions)
    stamp = _dt.datetime(2026, 9, 10, tzinfo=_dt.timezone.utc)
    first = build_page(predictions, report, None, record_updated=stamp)
    second = build_page(predictions, report, None, record_updated=stamp)
    assert first == second
    assert "last changed 2026-09-10" in first


def test_a_page_of_only_examples_shows_empty_figures_and_says_why():
    html = page([make(75, True, example=True), make(65, False, example=True)])
    assert "Every record here is an example" in html
    assert "There is no track record to score yet" in html
    assert "No resolved predictions yet" in html   # the chart's empty state
    assert "0.0000" not in html                    # never a flattering number
    assert html.count('class="entry ') == 2        # still listed in the log


def test_mixed_records_score_only_the_real_ones_and_the_page_says_so():
    html = page([make(80, True), make(90), make(50, True, example=True)])
    assert "0.0400" in html                        # (0.8 - 1)^2, the real record alone
    assert "1 of these records are examples" in html
    assert "excluded from every figure above" in html
    assert "Excludes 1 example record" in html
    assert html.count('class="entry ') == 3        # all three still listed


def test_log_heading_describes_what_is_listed_not_what_is_scored():
    """The log shows every record; the Standing counts only real ones. The heading must not lie."""
    html = page([make(80, True), make(90), make(50, True, example=True)])
    assert "1 open and 2 resolved" in html
    assert "including 1 example record that count" in html


def test_footer_counts_what_the_page_lists_not_what_it_scores():
    """Saying '0 records' under three visible entries reads as a bug even though the maths is right."""
    html = page([make(80, True), make(50, True, example=True)])
    assert "2 records listed" in html
    assert "0 records" not in html


def test_a_page_with_no_records_at_all_renders_and_says_so():
    """The state a fresh tracker starts in, and the one it returns to if every record is deleted."""
    html = page([])
    assert "No predictions have been recorded yet." in html
    assert "No resolved predictions yet" in html
    assert "0.0000" not in html
    assert "0 records listed" in html
    assert html.startswith("<!doctype html>")


def test_an_empty_record_set_is_not_shown_as_a_passed_verification():
    """Nothing to check is not the same as everything checked out."""
    html = page([], report=Report(verdicts=[]))
    assert "integrity--none" in html
    assert "nothing to verify" in html
    assert "integrity integrity--ok" not in html


def test_the_empty_chart_is_shorter_than_the_populated_one():
    """A full-height blank grid would dominate a tracker that has nothing to show yet."""
    import re as _re

    def view_height(svg):
        return float(_re.search(r'viewBox="0 0 \d+ ([\d.]+)"', svg).group(1))

    empty = calibration_svg(calibration([]))
    full = calibration_svg(calibration([make(75, True) for _ in range(6)]))
    assert view_height(empty) < view_height(full)
    assert "No resolved predictions yet" in empty
