# Forecast record

A public, tamper-evident record of dated probabilistic forecasts about economic indicators,
scored honestly over time.

The premise is that a forecasting track record is only worth anything if a sceptical reader can
check it. So: every prediction is a file committed to git before its outcome is known, the
fields that constitute the forecast are never rewritten, a script re-reads every historical
revision of every record on each build, and the scoring uses measures that cannot be gamed by
only predicting easy things.

The generated dashboard lives in [`../docs`](../docs) and is served by GitHub Pages.

## Using it

```
cd forecast
make new       # record a prediction: prompts, validates, writes, commits, rebuilds the site
make resolve   # settle one whose outcome is now known
make verify    # check every record against git history
make site      # rebuild the dashboard
make test      # run the test suite
```

`new-prediction` refuses vague claims. A claim must name the indicator, state a numeric
threshold with a direction, and point at a specific dated release; hedging words are rejected
outright. This is deliberately strict, and it will occasionally reject a claim that was
actually fine. That is the right way to err — a claim you can argue about after the fact
poisons the record permanently, whereas a rejected one costs thirty seconds.

Both scripts also accept flags (`--claim`, `--probability`, `--outcome`, ...) for non-interactive
use. `--no-commit` writes the file but leaves it uncommitted, which verification will then flag.

## How a prediction is stored

One JSON file per prediction in `predictions/`, named for its id:

```json
{
  "id": "P-0001",
  "created_at": "2026-09-10",
  "resolves_on": "2027-03-31",
  "claim": "...names the indicator, the threshold, and the release...",
  "probability": 65,
  "reasoning": "Two to five sentences of the forecaster's own rationale.",
  "resolution_source": "The exact dated publication that settles it",
  "outcome": null,
  "resolved_at": null,
  "resolution_note": null
}
```

`id`, `created_at`, `resolves_on`, `claim`, `probability`, `reasoning` and `resolution_source`
are **locked**. Only `outcome`, `resolved_at` and `resolution_note` are ever written afterwards.

## What verification actually proves

`make verify` checks two things against git, for every record:

1. `created_at` matches the date of the commit that first added the file.
2. No locked field differs in any commit in that file's history.

The second is the one that matters. A forecaster who quietly lowered a probability or softened
a claim after seeing the outcome would leave a current file that looks perfectly consistent —
only the history shows it.

**The honest limit:** git author dates are written by whoever makes the commit and can be
backdated on a local machine. These checks prove each record is consistent with its own commit
history. They do not prove that history was not manufactured. The independent evidence is the
hosting platform's public push log, which the repository owner cannot rewrite — so if you are
assessing this record sceptically, that is what to look at, and the page says so too.

## Scoring

- **Brier score** — mean squared error between stated probability and outcome. Lower is better,
  0 is perfect. Shown against the **baseline of 0.2500**, which is what you score by saying 50%
  to everything, because the raw number means nothing on its own.
- **Calibration** — predictions bucketed by stated confidence, each bucket's stated confidence
  plotted against how often those claims actually came true. Sample sizes are printed next to
  every point and buckets under five are drawn hollow and labelled thin. Wilson 90% intervals
  are drawn so that a small sample visibly looks like a small sample.
- **Resolution counts** — open and resolved, both always shown.

There is deliberately **no "percentage correct"**. It discards the probability attached to each
forecast, rewards timidity near 50%, and can be inflated by only ever predicting near-certain
things. A test asserts it stays absent.

## Layout

```
forecast/
  bin/          new-prediction, resolve, verify, build-site
  tracker/      model, claimcheck, scoring, integrity, render
  predictions/  one JSON file per prediction
  tests/        108 tests, including hand-computed scoring cases
  DESIGN.md     the design plan, written before the build
docs/           generated dashboard (GitHub Pages serves this)
```

Standard library only. No runtime dependencies, no JavaScript on the page, no build step. The
page is a single self-contained HTML file with inline CSS and inline SVG, so it renders the same
offline in ten years as it does today. `pytest` is needed only to run the tests.

## Publishing

GitHub Pages, set to deploy from this branch with the folder set to `/docs`. Nothing else to
configure; `docs/` is committed and every record change rebuilds it.

## The example records

`P-0001` to `P-0003` are placeholders with `"example": true`, naming fictional indicators and
fictional sources. No economic data was consulted to write or resolve them. They exist so the
dashboard has something to render. Delete them before the record means anything.
