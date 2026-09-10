"""Static site generation. No JavaScript, no build step, no runtime.

The whole page is one HTML file with inline CSS and inline SVG. That is a deliberate choice:
this thing needs to still render in several years with nobody maintaining it, and every
external dependency is a way for that to fail quietly.
"""

from __future__ import annotations

import datetime as _dt
import html
import math
from pathlib import Path

from .integrity import Report
from .model import Prediction
from .scoring import THIN_BUCKET, CalibrationBucket, RollingPoint, Standing, calibration, rolling_brier, standing

# ---------------------------------------------------------------------------------------
# Palette -- see DESIGN.md. Ochre is held at hue ~40 (brass/mustard) and never allowed toward
# the ~20 orange-red that reads terracotta.
# ---------------------------------------------------------------------------------------
INK = "#16222f"
INK_SOFT = "#5b6b79"
INK_FAINT = "#8f9ca7"
PAPER = "#f2efe9"
PAPER_RAISED = "#faf8f4"
OCHRE = "#9a7b3f"
OCHRE_BRIGHT = "#c9a45c"
AFFIRMED = "#4a7350"
REFUTED = "#9c4b41"
PANEL_GRID = "#2b3b4c"


def e(text: object) -> str:
    return html.escape(str(text), quote=True)


def fmt_score(value: float | None, places: int = 4) -> str:
    return "\u2014" if value is None else f"{value:.{places}f}"


def fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "\u2014"
    return f"{value * 100:+.1f}%"


# =======================================================================================
# The hero: calibration curve
# =======================================================================================

def calibration_svg(buckets: list[CalibrationBucket]) -> str:
    """Stated confidence against observed frequency, with Wilson 90% intervals.

    Design intent: this is the only loud object on the page. With a thin record the intervals
    are enormous and the chart looks uncertain -- that is the honest reading and it is left
    alone rather than smoothed into something reassuring.
    """
    width, height = 960, 580
    left, right, top, bottom = 92, 40, 44, 92
    plot_w = width - left - right
    plot_h = height - top - bottom

    def px(value: float) -> float:   # value 0-1 -> x
        return left + value * plot_w

    def py(value: float) -> float:   # value 0-1 -> y (inverted)
        return top + (1 - value) * plot_h

    populated = [b for b in buckets if not b.empty]
    total = sum(b.count for b in buckets)

    parts: list[str] = [
        (
            f'<svg viewBox="0 0 {width} {height}" class="calibration" role="img" '
            f'aria-labelledby="cal-title cal-desc" preserveAspectRatio="xMidYMid meet">'
        ),
        '<title id="cal-title">Calibration curve</title>',
        (
            f'<desc id="cal-desc">Stated confidence on the horizontal axis against observed '
            f'frequency on the vertical axis, for {total} resolved prediction'
            f'{"" if total == 1 else "s"}. A perfectly calibrated forecaster sits on the diagonal. '
            f'Vertical bars are Wilson 90 per cent intervals. The same numbers are given in the '
            f'table below the chart.</desc>'
        ),
        f'<rect width="{width}" height="{height}" fill="{INK}"/>',
    ]

    # Grid
    for step in range(11):
        value = step / 10
        x, y = px(value), py(value)
        major = step % 5 == 0
        stroke = OCHRE if major else PANEL_GRID
        opacity = "0.45" if major else "0.55"
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" '
            f'stroke="{stroke}" stroke-width="1" opacity="{opacity}"/>'
        )
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{stroke}" stroke-width="1" opacity="{opacity}"/>'
        )

    # Axis frame
    parts.append(
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="none" '
        f'stroke="{OCHRE}" stroke-width="1.5" opacity="0.7"/>'
    )

    # The reference diagonal: perfect calibration.
    parts.append(
        f'<line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(1):.1f}" y2="{py(1):.1f}" '
        f'stroke="{OCHRE_BRIGHT}" stroke-width="2" stroke-dasharray="7 6" opacity="0.9"/>'
    )
    # Set along the line rather than across it -- the plot is wider than it is tall, so the
    # diagonal is shallower than 45 degrees on screen and any horizontal label near it is crossed.
    diagonal_angle = math.degrees(math.atan2(-plot_h, plot_w))
    anchor_x, anchor_y = px(0.30), py(0.30)
    parts.append(
        f'<text transform="translate({anchor_x - 8:.1f},{anchor_y - 14:.1f}) '
        f'rotate({diagonal_angle:.2f})" text-anchor="middle" class="cal-note" '
        f'fill="{OCHRE_BRIGHT}">perfect calibration</text>'
    )

    # Axis ticks
    for step in range(0, 11, 2):
        value = step / 10
        parts.append(
            f'<text x="{px(value):.1f}" y="{top + plot_h + 26:.1f}" text-anchor="middle" '
            f'class="cal-tick" fill="{INK_FAINT}">{step * 10}</text>'
        )
        parts.append(
            f'<text x="{left - 14}" y="{py(value) + 5:.1f}" text-anchor="end" '
            f'class="cal-tick" fill="{INK_FAINT}">{step * 10}</text>'
        )

    parts.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h + 58:.1f}" text-anchor="middle" '
        f'class="cal-axis" fill="{PAPER}">stated confidence (%)</text>'
    )
    parts.append(
        f'<text transform="translate({left - 58},{top + plot_h / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" class="cal-axis" fill="{PAPER}">observed frequency (%)</text>'
    )

    if not populated:
        parts.append(
            f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h / 2 - 8:.1f}" '
            f'text-anchor="middle" class="cal-empty" fill="{PAPER}">No resolved predictions yet</text>'
        )
        parts.append(
            f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h / 2 + 22:.1f}" '
            f'text-anchor="middle" class="cal-note" fill="{INK_FAINT}">'
            f'The curve appears once predictions begin to resolve.</text>'
        )
        parts.append("</svg>")
        return "\n".join(parts)

    # Wilson intervals first, so points sit on top.
    for bucket in populated:
        assert bucket.mean_stated is not None and bucket.ci_low is not None and bucket.ci_high is not None
        x = px(bucket.mean_stated)
        y_low, y_high = py(bucket.ci_low), py(bucket.ci_high)
        dash = ' stroke-dasharray="4 4"' if bucket.thin else ""
        opacity = "0.55" if bucket.thin else "0.85"
        parts.append(
            f'<line x1="{x:.1f}" y1="{y_low:.1f}" x2="{x:.1f}" y2="{y_high:.1f}" '
            f'stroke="{OCHRE_BRIGHT}" stroke-width="2"{dash} opacity="{opacity}"/>'
        )
        for cap_y in (y_low, y_high):
            parts.append(
                f'<line x1="{x - 7:.1f}" y1="{cap_y:.1f}" x2="{x + 7:.1f}" y2="{cap_y:.1f}" '
                f'stroke="{OCHRE_BRIGHT}" stroke-width="2" opacity="{opacity}"/>'
            )

    # Connecting path through well-populated buckets only. A line drawn through two-sample
    # buckets would imply a trend that is not there.
    solid = [b for b in populated if not b.thin]
    if len(solid) > 1:
        points = " ".join(
            f"{px(b.mean_stated):.1f},{py(b.hit_rate):.1f}" for b in solid  # type: ignore[arg-type]
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{PAPER}" stroke-width="2.5" opacity="0.85"/>'
        )

    for bucket in populated:
        assert bucket.mean_stated is not None and bucket.hit_rate is not None
        x, y = px(bucket.mean_stated), py(bucket.hit_rate)
        radius = 6 + 2.6 * (bucket.count ** 0.5)
        radius = min(radius, 26)
        if bucket.thin:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="none" '
                f'stroke="{PAPER}" stroke-width="2" stroke-dasharray="3 3" opacity="0.75"/>'
            )
        else:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{PAPER}" '
                f'stroke="{INK}" stroke-width="1.5"/>'
            )
        label = f'n={bucket.count}{" (thin)" if bucket.thin else ""}'
        label_x, anchor = x + radius + 9, "start"
        if label_x + 8 * len(label) > left + plot_w:
            label_x, anchor = x - radius - 9, "end"
        label_y = min(max(y + 4, top + 16), top + plot_h - 8)
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" class="cal-count" '
            f'fill="{PAPER if not bucket.thin else INK_FAINT}">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def calibration_legend() -> str:
    """Legend as HTML rather than inside the SVG, so it reflows and stays readable on a phone."""
    swatches = [
        (
            (
                f'<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" '
                f'fill="{INK}" stroke="{INK}" stroke-width="1.5"/></svg>'
            ),
            f"bucket holding {THIN_BUCKET} or more resolved predictions, sized by count",
        ),
        (
            (
                f'<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" '
                f'stroke="{INK}" stroke-width="2" stroke-dasharray="3 3"/></svg>'
            ),
            f"fewer than {THIN_BUCKET}: shown, but too thin to read anything into",
        ),
        (
            (
                f'<svg viewBox="0 0 16 16" aria-hidden="true"><line x1="8" y1="1" x2="8" y2="15" '
                f'stroke="{OCHRE}" stroke-width="2"/><line x1="4" y1="1" x2="12" y2="1" stroke="{OCHRE}" '
                f'stroke-width="2"/><line x1="4" y1="15" x2="12" y2="15" stroke="{OCHRE}" stroke-width="2"/></svg>'
            ),
            "Wilson 90% interval \u2014 tall bars mean the sample is too small to tell",
        ),
    ]
    items = "".join(
        f"<li><span class='swatch'>{swatch}</span><span>{e(text)}</span></li>"
        for swatch, text in swatches
    )
    return f"<ul class='legend'>{items}</ul>"


def calibration_table(buckets: list[CalibrationBucket]) -> str:
    """The same numbers as the chart, in a table. For screen readers, and for sceptics."""
    rows: list[str] = []
    for bucket in buckets:
        if bucket.empty:
            rows.append(
                f"<tr class='is-empty'><th scope='row'>{e(bucket.label)}</th>"
                f"<td class='num'>0</td><td class='num'>\u2014</td><td class='num'>\u2014</td>"
                f"<td class='num'>\u2014</td><td>no predictions in this range</td></tr>"
            )
            continue
        assert bucket.mean_stated is not None and bucket.hit_rate is not None
        note = f"thin \u2014 {bucket.count} resolved, not meaningful" if bucket.thin else ""
        rows.append(
            f"<tr><th scope='row'>{e(bucket.label)}</th>"
            f"<td class='num'>{bucket.count}</td>"
            f"<td class='num'>{bucket.hits}</td>"
            f"<td class='num'>{bucket.mean_stated * 100:.1f}%</td>"
            f"<td class='num'>{bucket.hit_rate * 100:.1f}%</td>"
            f"<td>{e(note)}</td></tr>"
        )
    return (
        "<table class='data-table'>"
        "<caption>Calibration buckets. Ranges include the lower bound and exclude the upper, "
        "except the top bucket which includes 100%.</caption>"
        "<thead><tr><th scope='col'>Stated</th><th scope='col'>Resolved</th>"
        "<th scope='col'>Came true</th><th scope='col'>Mean stated</th>"
        "<th scope='col'>Observed</th><th scope='col'>Note</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


# =======================================================================================
# Rolling Brier -- deliberately small and quiet; the calibration curve is the hero.
# =======================================================================================

def rolling_svg(points: list[RollingPoint]) -> str:
    width, height = 640, 170
    left, right, top, bottom = 44, 16, 18, 34
    plot_w, plot_h = width - left - right, height - top - bottom

    if not points:
        return (
            f'<svg viewBox="0 0 {width} {height}" class="rolling" role="img" aria-label="Rolling '
            f'Brier score: no resolved predictions yet.">'
            f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" class="roll-note" '
            f'fill="{INK_SOFT}">Nothing resolved yet</text></svg>'
        )

    ceiling = max(0.3, max(p.brier_to_date for p in points) * 1.25)

    def px(index: int) -> float:
        if len(points) == 1:
            return left + plot_w / 2
        return left + (index / (len(points) - 1)) * plot_w

    def py(value: float) -> float:
        return top + (1 - min(value / ceiling, 1.0)) * plot_h

    parts = [
        (
            f'<svg viewBox="0 0 {width} {height}" class="rolling" role="img" '
            f'aria-label="Cumulative Brier score after each of {len(points)} resolutions, against '
            f'the 0.25 baseline. Lower is better.">'
        ),
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="{INK_FAINT}" stroke-width="1"/>',
        (
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
            f'stroke="{INK_FAINT}" stroke-width="1"/>'
        ),
    ]

    baseline_y = py(0.25)
    parts.append(
        f'<line x1="{left}" y1="{baseline_y:.1f}" x2="{left + plot_w}" y2="{baseline_y:.1f}" '
        f'stroke="{OCHRE}" stroke-width="1.5" stroke-dasharray="6 5"/>'
    )
    parts.append(
        f'<text x="{left + 6}" y="{baseline_y - 8:.1f}" text-anchor="start" class="roll-note" '
        f'fill="{OCHRE}">baseline 0.2500</text>'
    )
    for value in (0.0, ceiling):
        parts.append(
            f'<text x="{left - 8}" y="{py(value) + 4:.1f}" text-anchor="end" class="roll-tick" '
            f'fill="{INK_FAINT}">{value:.2f}</text>'
        )

    if len(points) > 1:
        path = " ".join(f"{px(i):.1f},{py(p.brier_to_date):.1f}" for i, p in enumerate(points))
        parts.append(f'<polyline points="{path}" fill="none" stroke="{INK}" stroke-width="2.5"/>')
    for index, point in enumerate(points):
        parts.append(
            f'<circle cx="{px(index):.1f}" cy="{py(point.brier_to_date):.1f}" r="4" fill="{INK}"/>'
        )
    last = points[-1]
    parts.append(
        f'<text x="{px(len(points) - 1):.1f}" y="{py(last.brier_to_date) - 12:.1f}" '
        f'text-anchor="end" class="roll-value" fill="{INK}">{last.brier_to_date:.4f}</text>'
    )
    parts.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 8}" text-anchor="middle" class="roll-note" '
        f'fill="{INK_SOFT}">resolutions, in order ({len(points)})</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


# =======================================================================================
# Page
# =======================================================================================

def _integrity_block(report: Report | None, error: str | None) -> str:
    if error:
        return (
            f"<p class='integrity integrity--unknown'><span class='integrity-mark'>?</span>"
            f"Verification could not be run: {e(error)}. Treat the record as unverified.</p>"
        )
    assert report is not None
    if report.ok:
        body = (
            f"<p class='integrity integrity--ok'><span class='integrity-mark'>&#10003;</span>"
            f"{e(report.summary)}</p>"
        )
    else:
        items = "".join(
            f"<li><code>{e(v.prediction_id)}</code> {e(' '.join(v.problems))}</li>"
            for v in report.failures
        )
        body = (
            f"<p class='integrity integrity--bad'><span class='integrity-mark'>&#33;</span>"
            f"{e(report.summary)}</p><ul class='integrity-list'>{items}</ul>"
        )
    return body + f"<p class='caveat'>{e(report.caveat)}</p>"


def _standing_block(result: Standing) -> str:
    cells = [
        ("Brier score", fmt_score(result.brier), "lower is better"),
        ("Baseline", fmt_score(result.baseline), "always saying 50%"),
        ("Skill vs baseline", fmt_signed_pct(result.skill), "share of baseline error removed"),
        ("Resolved", str(result.resolved), f"{result.hits} affirmed, {result.misses} refuted"),
        ("Open", str(result.open), "not yet settled"),
    ]
    figures = "".join(
        f"<div class='figure'><dt>{e(label)}</dt>"
        f"<dd class='figure-value num'>{e(value)}</dd>"
        f"<dd class='figure-note'>{e(note)}</dd></div>"
        for label, value, note in cells
    )
    return f"<dl class='standing'>{figures}</dl>"


def _outcome_mark(prediction: Prediction) -> str:
    if not prediction.resolved:
        return "<span class='mark mark--open'>open</span>"
    if prediction.outcome:
        return "<span class='mark mark--true'><span aria-hidden='true'>&#9679;</span> affirmed</span>"
    return "<span class='mark mark--false'><span aria-hidden='true'>&#9675;</span> refuted</span>"


def _log_entry(prediction: Prediction) -> str:
    resolution = ""
    if prediction.resolved:
        assert prediction.resolved_at is not None
        verdict = "came true" if prediction.outcome else "did not come true"
        resolution = (
            f"<p class='entry-resolution'>Resolved {e(prediction.resolved_at.isoformat())}: "
            f"the claim <strong>{e(verdict)}</strong>. {e(prediction.resolution_note)}</p>"
        )
    example = "<span class='tag'>example record</span>" if prediction.example else ""
    return f"""
<article class="entry entry--{'resolved' if prediction.resolved else 'open'}">
  <div class="entry-id"><span class="num">{e(prediction.id)}</span>{example}</div>
  <div class="entry-body">
    <p class="entry-claim">{e(prediction.claim)}</p>
    <p class="entry-meta">
      <span>Made <time datetime="{e(prediction.created_at.isoformat())}" class="num">{e(prediction.created_at.isoformat())}</time></span>
      <span>Resolves <time datetime="{e(prediction.resolves_on.isoformat())}" class="num">{e(prediction.resolves_on.isoformat())}</time></span>
      <span>Source: {e(prediction.resolution_source)}</span>
    </p>
    {resolution}
    <details class="entry-reasoning">
      <summary>Reasoning as written at the time</summary>
      <p>{e(prediction.reasoning)}</p>
    </details>
  </div>
  <div class="entry-probability"><span class="num">{prediction.probability}</span><span class="pct">%</span></div>
  <div class="entry-outcome">{_outcome_mark(prediction)}</div>
</article>"""


EXPLAINER = """
<h2>What these numbers mean</h2>
<p>
  A forecast of &ldquo;70% chance&rdquo; is not right or wrong on its own. You cannot judge it from a
  single outcome, only from many. So this page does not report a percentage of predictions that
  came true &mdash; that measure ignores the confidence attached to each one, and it rewards a
  forecaster who only ever predicts near-certainties.
</p>
<p>
  The <strong>Brier score</strong> is the average squared distance between what was claimed and
  what happened. Say 90% and it comes true, the penalty is (0.9&nbsp;&minus;&nbsp;1)&sup2;&nbsp;=&nbsp;0.01.
  Say 90% and it does not, the penalty is (0.9&nbsp;&minus;&nbsp;0)&sup2;&nbsp;=&nbsp;0.81. Lower is
  better; 0 is perfect. The number is meaningless in isolation, so it is shown against the
  <strong>baseline</strong> of 0.2500 &mdash; the score you get by saying 50% to everything and
  knowing nothing. Beating the baseline is the minimum bar, not an achievement.
</p>
<p>
  <strong>Calibration</strong> asks a different question: when this forecaster says 70%, does the
  thing happen about 70% of the time? Predictions are grouped by stated confidence and each group
  is plotted against how often those claims actually came true. A perfectly calibrated forecaster
  sits on the diagonal. Sitting above it means being too cautious; below it means being
  overconfident, which is the common failure.
</p>
<p>
  Calibration needs volume to mean anything. A bucket holding two predictions tells you nothing at
  all, so the chart draws thin buckets hollow and prints the sample size next to every point. The
  vertical bars are 90% confidence intervals: where they are tall, the honest reading is that we do
  not yet know. They shrink only as the record grows.
</p>
"""


def _page_css() -> str:
    return f"""
:root {{
  color-scheme: light;
  --ink: {INK};
  --ink-soft: {INK_SOFT};
  --ink-faint: {INK_FAINT};
  --paper: {PAPER};
  --paper-raised: {PAPER_RAISED};
  --ochre: {OCHRE};
  --affirmed: {AFFIRMED};
  --refuted: {REFUTED};
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", "Liberation Sans", Arial, sans-serif;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Charter, "Bitstream Charter",
           Georgia, "Liberation Serif", serif;
  --measure: 68ch;
  --rule: 1px solid rgba(22, 34, 47, 0.16);
  --rule-strong: 1px solid rgba(22, 34, 47, 0.42);
}}

*, *::before, *::after {{ box-sizing: border-box; }}

html {{ -webkit-text-size-adjust: 100%; }}

body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.55;
  font-variant-numeric: tabular-nums lining;
  font-feature-settings: "tnum" 1, "lnum" 1;
}}

/* Every numeral on the page is tabular and fixed-width, so columns align even where the
   fallback face lacks true tabular figures. */
.num, time, .figure-value, .data-table td, .data-table th {{
  font-variant-numeric: tabular-nums lining;
  font-feature-settings: "tnum" 1, "lnum" 1;
  letter-spacing: 0.01em;
}}

.wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 28px; }}

a {{ color: var(--ink); text-decoration-thickness: 1px; text-underline-offset: 3px; }}
a:hover {{ color: var(--ochre); }}

:focus-visible {{
  outline: 2px solid var(--ochre);
  outline-offset: 3px;
}}

.skip {{
  position: absolute; left: -9999px; top: 0;
  background: var(--ink); color: var(--paper); padding: 12px 18px; z-index: 10;
}}
.skip:focus {{ left: 0; }}

/* ---- masthead ---------------------------------------------------------------------- */
.masthead {{ border-bottom: var(--rule-strong); padding: 42px 0 26px; }}
.masthead h1 {{
  font-size: clamp(1.55rem, 3.4vw, 2.15rem);
  line-height: 1.15; margin: 0 0 10px; font-weight: 600; letter-spacing: -0.015em;
}}
.standfirst {{
  margin: 0 0 20px; max-width: var(--measure);
  color: var(--ink-soft); font-size: 1.02rem;
}}

.integrity {{
  display: flex; gap: 10px; align-items: baseline;
  margin: 0; padding: 12px 0 0; border-top: var(--rule);
  max-width: var(--measure); font-size: 0.94rem;
}}
.integrity-mark {{
  flex: none; width: 1.35em; height: 1.35em; line-height: 1.3em; text-align: center;
  border: 1px solid currentColor; font-size: 0.85em;
}}
.integrity--ok {{ color: var(--affirmed); }}
.integrity--bad, .integrity--unknown {{ color: var(--refuted); }}
.integrity-list {{ margin: 10px 0 0; padding-left: 20px; color: var(--refuted); font-size: 0.9rem; }}
.caveat {{
  margin: 10px 0 0; max-width: var(--measure);
  font-family: var(--serif); font-size: 0.92rem; color: var(--ink-soft);
}}

.notice {{
  margin: 22px 0 0; padding: 14px 18px;
  border-left: 3px solid var(--ochre); background: var(--paper-raised);
  max-width: var(--measure); font-size: 0.94rem;
}}
.notice strong {{ font-weight: 600; }}

/* ---- section scaffolding ----------------------------------------------------------- */
section {{ padding: 46px 0; border-top: var(--rule); }}
section:first-of-type {{ border-top: none; }}
h2 {{ font-size: 1.16rem; font-weight: 600; margin: 0 0 22px; letter-spacing: -0.005em; }}
h2 .h2-note {{ font-weight: 400; color: var(--ink-soft); }}

/* ---- standing ---------------------------------------------------------------------- */
.standing {{
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 0; margin: 0; border-top: var(--rule-strong); border-bottom: var(--rule-strong);
}}
.figure {{ padding: 18px 20px 16px; border-left: var(--rule); }}
.figure:first-child {{ border-left: none; padding-left: 0; }}
.figure dt {{ font-size: 0.79rem; color: var(--ink-soft); margin-bottom: 6px; }}
.figure-value {{
  margin: 0; font-size: clamp(1.5rem, 2.7vw, 1.95rem);
  font-weight: 500; line-height: 1.1; letter-spacing: -0.02em;
}}
.figure-note {{ margin: 5px 0 0; font-size: 0.79rem; color: var(--ink-faint); }}

.rolling-row {{
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 320px);
  gap: 40px; align-items: end; margin-top: 34px;
}}
.rolling {{ width: 100%; height: auto; display: block; }}
.rolling-caption {{ font-family: var(--serif); font-size: 0.92rem; color: var(--ink-soft); margin: 0; }}
.roll-note {{ font-size: 12px; font-family: var(--sans); }}
.roll-tick {{ font-size: 11px; font-family: var(--sans); }}
.roll-value {{ font-size: 14px; font-weight: 600; font-family: var(--sans); }}

/* ---- hero -------------------------------------------------------------------------- */
.hero {{ padding-bottom: 20px; }}
.panel {{ background: {INK}; padding: 12px 12px 4px; }}
.calibration {{ width: 100%; height: auto; display: block; }}
.cal-tick {{ font-size: 14px; font-family: var(--sans); font-variant-numeric: tabular-nums; }}
.cal-axis {{ font-size: 15px; font-family: var(--sans); }}
.cal-count {{ font-size: 13px; font-family: var(--sans); font-variant-numeric: tabular-nums; }}
.cal-note {{ font-size: 13px; font-family: var(--sans); }}
.cal-empty {{ font-size: 22px; font-family: var(--sans); }}

.legend {{
  list-style: none; margin: 16px 0 0; padding: 0;
  display: flex; flex-wrap: wrap; gap: 10px 34px;
  font-size: 0.85rem; color: var(--ink-soft);
}}
.legend li {{ display: flex; align-items: center; gap: 9px; }}
.legend .swatch {{ flex: none; width: 16px; height: 16px; }}
.legend svg {{ width: 16px; height: 16px; display: block; }}

details.numbers {{ margin-top: 20px; }}
details.numbers > summary {{
  cursor: pointer; font-size: 0.92rem; color: var(--ink-soft);
  padding: 8px 0; border-bottom: var(--rule);
}}
details.numbers > summary:hover {{ color: var(--ochre); }}

.table-scroll {{ overflow-x: auto; }}
.data-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 0.9rem; }}
.data-table caption {{
  text-align: left; color: var(--ink-soft); font-size: 0.86rem;
  padding-bottom: 12px; max-width: var(--measure);
}}
.data-table th, .data-table td {{ padding: 8px 14px 8px 0; text-align: left; border-bottom: var(--rule); }}
.data-table thead th {{ border-bottom: var(--rule-strong); font-weight: 600; font-size: 0.82rem; }}
.data-table .num {{ text-align: right; padding-right: 22px; }}
.data-table tbody th {{ font-weight: 500; }}
.data-table tr.is-empty {{ color: var(--ink-faint); }}

/* ---- explainer --------------------------------------------------------------------- */
.explainer {{ font-family: var(--serif); }}
.explainer h2 {{ font-family: var(--sans); }}
.explainer p {{ max-width: var(--measure); font-size: 1.03rem; line-height: 1.66; margin: 0 0 18px; }}
.explainer strong {{ font-weight: 600; }}

/* ---- the log ----------------------------------------------------------------------- */
.entry {{
  display: grid;
  grid-template-columns: 7.5rem minmax(0, 1fr) 5rem 7.5rem;
  gap: 0 24px; padding: 22px 0; border-bottom: var(--rule); align-items: start;
}}
.entry:first-of-type {{ border-top: var(--rule-strong); }}
.entry-id {{ font-size: 0.86rem; color: var(--ink-soft); }}
.tag {{
  display: block; margin-top: 6px; font-size: 0.7rem; color: var(--ochre);
  border: 1px solid currentColor; padding: 1px 5px; width: fit-content;
}}
.entry-claim {{ margin: 0 0 8px; font-size: 1.01rem; line-height: 1.45; }}
.entry-meta {{
  margin: 0; font-size: 0.82rem; color: var(--ink-soft);
  display: flex; flex-wrap: wrap; gap: 4px 20px;
}}
.entry-resolution {{
  margin: 12px 0 0; font-size: 0.92rem; padding-left: 14px;
  border-left: 2px solid var(--ink-faint); max-width: var(--measure);
}}
.entry--resolved .entry-resolution {{ border-left-color: currentColor; }}
.entry-reasoning {{ margin-top: 12px; }}
.entry-reasoning > summary {{
  cursor: pointer; font-size: 0.86rem; color: var(--ink-soft); width: fit-content;
}}
.entry-reasoning > summary:hover {{ color: var(--ochre); }}
.entry-reasoning p {{
  margin: 10px 0 0; font-family: var(--serif); font-size: 0.98rem;
  max-width: var(--measure); padding-left: 14px; border-left: 1px solid var(--ink-faint);
}}
.entry-probability {{ text-align: right; font-size: 1.5rem; font-weight: 500; letter-spacing: -0.02em; }}
.entry-probability .pct {{ font-size: 0.85rem; color: var(--ink-soft); margin-left: 1px; }}
.entry-outcome {{ text-align: right; padding-top: 6px; }}

.mark {{ font-size: 0.86rem; white-space: nowrap; }}
.mark--true {{ color: var(--affirmed); }}
.mark--false {{ color: var(--refuted); }}
.mark--open {{ color: var(--ink-faint); }}

footer {{
  border-top: var(--rule-strong); padding: 30px 0 60px;
  font-size: 0.86rem; color: var(--ink-soft);
}}
footer p {{ margin: 0 0 8px; max-width: var(--measure); }}

/* ---- responsive -------------------------------------------------------------------- */
@media (max-width: 900px) {{
  .standing {{ grid-template-columns: repeat(2, 1fr); }}
  .figure {{ border-left: none; border-top: var(--rule); padding-left: 0; }}
  .figure:first-child, .figure:nth-child(2) {{ border-top: none; }}
  .rolling-row {{ grid-template-columns: 1fr; gap: 20px; align-items: start; }}
}}

@media (max-width: 720px) {{
  /* The chart scales by viewBox, so its type must scale up to stay legible on a phone. */
  .cal-tick {{ font-size: 26px; }}
  .cal-axis {{ font-size: 28px; }}
  .cal-count {{ font-size: 25px; }}
  .cal-note {{ font-size: 25px; }}
  .cal-empty {{ font-size: 34px; }}
  .legend {{ gap: 8px 20px; font-size: 0.82rem; }}
  .wrap {{ padding: 0 18px; }}
  section {{ padding: 32px 0; }}
  .entry {{ grid-template-columns: 1fr auto; gap: 4px 16px; }}
  .entry-id {{ grid-column: 1; grid-row: 1; }}
  .entry-outcome {{ grid-column: 2; grid-row: 1; text-align: right; padding-top: 0; }}
  .entry-body {{ grid-column: 1 / -1; grid-row: 2; margin-top: 8px; }}
  .entry-probability {{ grid-column: 1 / -1; grid-row: 3; text-align: left; margin-top: 10px; }}
  .tag {{ display: inline-block; margin-top: 0; margin-left: 8px; }}
  .panel {{ padding: 6px 6px 2px; margin: 0 -18px; }}
}}

@media (max-width: 480px) {{
  .standing {{ grid-template-columns: 1fr; }}
  .figure {{ border-top: var(--rule); }}
  .figure:nth-child(2) {{ border-top: var(--rule); }}
  .figure:first-child {{ border-top: none; }}
}}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    animation-duration: 0.001ms !important; animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important; scroll-behavior: auto !important;
  }}
}}

@media print {{
  .panel {{ background: {INK} !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .entry-reasoning[open] {{ break-inside: avoid; }}
}}
"""


def build_page(
    predictions: list[Prediction],
    report: Report | None,
    integrity_error: str | None = None,
    generated_at: _dt.datetime | None = None,
) -> str:
    result = standing(predictions)
    buckets = calibration(predictions)
    rolling = rolling_brier(predictions)
    stamp = (generated_at or _dt.datetime.now(_dt.timezone.utc)).replace(microsecond=0)

    example_count = sum(1 for p in predictions if p.example)
    notice = ""
    if example_count:
        all_examples = example_count == len(predictions)
        notice = (
            f"<div class='notice'><strong>{'Every record here is an example.' if all_examples else f'{example_count} of these records are examples.'}</strong> "
            "They contain placeholder text, not real forecasts. The indicators and sources they "
            "name are fictional and no economic data was consulted to write or resolve them. "
            "They exist so the dashboard has something to render before a real record begins.</div>"
        )

    entries = "\n".join(_log_entry(p) for p in predictions) or (
        "<p class='entry-meta'>No predictions have been recorded yet.</p>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forecast record</title>
<meta name="description" content="A dated, locked, publicly scored record of probabilistic economic forecasts.">
<meta name="robots" content="index, follow">
<style>{_page_css()}</style>
</head>
<body>
<a class="skip" href="#log">Skip to the prediction log</a>

<header class="masthead">
  <div class="wrap">
    <h1>Forecast record</h1>
    <p class="standfirst">
      Dated probabilistic predictions about economic indicators, written down before the outcome
      is known, locked by commit, and scored afterwards whether they went well or badly.
    </p>
    {_integrity_block(report, integrity_error)}
    {notice}
  </div>
</header>

<main>
  <section class="standing-section">
    <div class="wrap">
      <h2>Standing <span class="h2-note">&mdash; all predictions, resolved and open</span></h2>
      {_standing_block(result)}
      <div class="rolling-row">
        <div>{rolling_svg(rolling)}</div>
        <p class="rolling-caption">
          The cumulative Brier score after each resolution. It should sit below the dashed
          baseline; if it does not, the forecasts are worse than saying 50% to everything.
          Early points move sharply because a mean over few results is mostly noise.
        </p>
      </div>
    </div>
  </section>

  <section class="hero">
    <div class="wrap">
      <h2>Calibration <span class="h2-note">&mdash; stated confidence against what actually happened</span></h2>
      <div class="panel">{calibration_svg(buckets)}</div>
      {calibration_legend()}
      <details class="numbers">
        <summary>The numbers behind this chart</summary>
        <div class="table-scroll">{calibration_table(buckets)}</div>
      </details>
    </div>
  </section>

  <section class="explainer">
    <div class="wrap">{EXPLAINER}</div>
  </section>

  <section id="log">
    <div class="wrap">
      <h2>The log <span class="h2-note">&mdash; newest first, {result.open} open and {result.resolved} resolved, nothing withheld</span></h2>
      {entries}
    </div>
  </section>
</main>

<footer>
  <div class="wrap">
    <p>
      Each prediction is a JSON file committed to a public git repository. The fields that
      constitute the forecast &mdash; the claim, the probability, the reasoning, the dates &mdash;
      are never rewritten; only the outcome and its note are added later. A verification script
      re-reads every historical revision of every record on each build and reports above.
    </p>
    <p>Page generated {e(stamp.isoformat())} from {result.total} record{"" if result.total == 1 else "s"}.</p>
  </div>
</footer>
</body>
</html>
"""


def write_site(
    predictions: list[Prediction],
    report: Report | None,
    output: Path,
    integrity_error: str | None = None,
) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    index = output / "index.html"
    index.write_text(build_page(predictions, report, integrity_error), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    return index
