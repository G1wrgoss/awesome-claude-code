# Design plan

Written before implementation, checked against the "deliberately avoid" list, revised where
anything read as a default. Kept in the repo so the reasoning is auditable like everything else.

## Concept

A ledger, not a dashboard. The page should read as a bound record that happens to be on the web:
ruled lines, a masthead, a single continuous log. Nothing that suggests a product with metrics
to grow. The governing question for every element: *would this appear in a ship's log?* If it
only appears in SaaS marketing, it is cut.

Structural decision: **no cards anywhere.** Hierarchy comes from hairline rules, spacing and
type size alone. This removes the single biggest tell of a templated dashboard and forces the
layout to earn its structure.

## Palette

| Role | Value | Use |
|---|---|---|
| Ink | `#16222f` | Body text, rules, the hero panel ground |
| Ink (muted) | `#5b6b79` | Secondary text, axis labels |
| Paper | `#f2efe9` | Page ground |
| Paper (raised) | `#faf8f4` | The log's alternating bands, ruled table fills |
| Ochre | `#9a7b3f` | Structure only: the calibration reference diagonal, rules that carry meaning, focus ring |
| Affirmed | `#4a7350` | Resolved-true marks only |
| Refuted | `#9c4b41` | Resolved-false marks only |

Two deliberate corrections against the avoid list:

- **Not cream + terracotta.** The brief's "warm off-white" and "muted ochre" land exactly on that
  cliché if taken at face value. So the ground is pulled to a warm *grey* paper (`#f2efe9`,
  hue ~40° but only ~8% saturation) rather than a yellow cream, and the ochre is held at hue 40°
  — a mustard/brass — never allowed toward the 20° orange-red that reads terracotta.
- **Red/green are locked to outcomes.** They appear nowhere else: not on links, not on the
  summary figures, not on the open/resolved counts. The eye should be able to scan the log and
  read accuracy from colour alone with zero false positives.

No gradients. No shadows. Border-radius is 0 throughout.

## Typography

- **Numerals and interface:** one grotesk, system stack led by faces that ship true tabular
  figures (SF / Segoe UI / Roboto), with `font-variant-numeric: tabular-nums lining`. Every
  numeral in the page — scores, probabilities, dates, counts — is tabular and right-aligned in
  fixed-width columns, so columns stay aligned even on a system whose fallback lacks `tnum`.
  Belt and braces, because the alternative is a webfont dependency that can break unattended.
- **Explainer prose:** a serif (Iowan/Charter/Georgia stack). Clearly distinct — different
  skeleton, not a different weight of the same thing — and used *only* for the explainer and
  the reasoning text. It marks "this is a person writing" versus "this is the record".

## Layout

1. **Masthead** — rule, project name, one line saying what this is, and the integrity status
   sentence. The integrity line sits at the top, not buried, because it is the claim the whole
   page rests on.
2. **Standing** — a single ruled row of figures: Brier, baseline, skill, resolved, open.
   Set as a ledger row, not five cards.
3. **Calibration curve** — the hero. A deep-ink panel, the only inverted region on the page,
   roughly full-width and tall. Ochre dashed diagonal for perfect calibration, bucket points
   sized by sample count, Wilson 90% intervals drawn as vertical bars. Thin buckets (n < 5) are
   drawn hollow and explicitly labelled. With little data the intervals are enormous — that is
   the honest signal and it is left visible rather than smoothed away.
4. **Explainer** — serif, narrow measure, directly under the chart where a reader who does not
   know what a Brier score is will actually meet it.
5. **The log** — one continuous ruled list, newest first, open and resolved interleaved.
   Each entry: id, dates, claim, probability, outcome mark. Reasoning behind a native
   `<details>` disclosure — no JS, keyboard-operable for free.

## Avoid-list check

| Named default | Status |
|---|---|
| Cream ground + terracotta accents | Corrected — warm grey paper, hue-locked mustard ochre |
| All-caps eyebrow labels above headings | None. Sections are marked by a hairline rule + sentence-case heading |
| Identical rounded cards, soft grey shadows | No cards, no shadows, no radius anywhere |
| "01 / 02 / 03" numbered markers | None. The only numbers are data (prediction ids, counts) |
| Arrows appended to link text | None |
| Fade-and-slide-up entrance animations | None. The page has no entrance animation at all |

## Motion and access

The only motion is the native disclosure toggle. `prefers-reduced-motion` removes it. Focus is
visible everywhere as a 2px ochre outline with offset — never removed. Colour is never the sole
carrier of meaning: every outcome has a text label and a glyph beside its colour. Layout is a
single column below 720px; the chart scales by viewBox and its labels drop to a coarser interval.
