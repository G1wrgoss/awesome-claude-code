"""Scoring for probabilistic forecasts.

Deliberately *not* implemented here: "percentage correct". For probabilistic forecasts it is
the wrong measure -- it throws away the probability, rewards timid predictions near 50%, and
can be gamed by only ever predicting near-certain things. The headline is the Brier score,
shown against the always-50% baseline so a reader can see whether the forecaster beats a coin.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .model import Prediction

# Always predicting 50% scores (0.5 - outcome)^2 = 0.25 on every question, whatever happens.
# It is the honest "I know nothing" reference point.
BASELINE_BRIER = 0.25

# Buckets are [low, high) except the last, which is [90, 100] so that a stated 100% has a home.
BUCKET_WIDTH = 10
BUCKET_COUNT = 10

# Below this many resolved predictions a bucket is displayed but explicitly marked as too thin
# to read anything into.
THIN_BUCKET = 5

# z for a two-sided 90% interval.
_Z_90 = 1.6448536269514722


def scored(predictions: Iterable[Prediction]) -> list[Prediction]:
    """The records that count toward the track record.

    Example records are placeholders with fabricated outcomes, seeded so a fresh deployment has
    something to display. Letting them reach the scoring maths would put invented results into
    the headline number, which is precisely the kind of flattery this project exists to avoid.
    Every scoring function filters through here rather than trusting its callers to remember.
    """
    return [p for p in predictions if not p.example]


def brier_score(predictions: Sequence[Prediction]) -> float | None:
    """Mean squared error between stated probability and outcome. Lower is better.

    Returns None when nothing has resolved -- callers must render that as "no data", never as 0.
    """
    resolved = [p for p in scored(predictions) if p.resolved]
    if not resolved:
        return None
    total = 0.0
    for prediction in resolved:
        outcome = 1.0 if prediction.outcome else 0.0
        total += (prediction.p - outcome) ** 2
    return total / len(resolved)


def skill_score(brier: float | None, baseline: float = BASELINE_BRIER) -> float | None:
    """Fraction of the baseline's error removed. 0 means no better than always saying 50%.

    Positive is better than the coin, negative is worse. Unbounded below, capped at 1.
    """
    if brier is None:
        return None
    if baseline <= 0:
        raise ValueError("baseline Brier score must be positive")
    return 1.0 - (brier / baseline)


def bucket_index(probability: int) -> int:
    """Which calibration bucket a stated probability falls in.

    Edges are half-open upward -- 10 lands in the 10-20 bucket, not 0-10 -- with 100 folded
    into the top bucket.
    """
    if not 0 <= probability <= 100:
        raise ValueError(f"probability must be within 0-100, got {probability}")
    if probability == 100:
        return BUCKET_COUNT - 1
    return probability // BUCKET_WIDTH


def wilson_interval(hits: int, n: int, z: float = _Z_90) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because the buckets here are small, and the
    normal interval produces nonsense (bounds outside 0-1, zero width at 0 hits) exactly
    where this project is most at risk of overclaiming.
    """
    if n <= 0:
        raise ValueError("wilson_interval needs at least one observation")
    if not 0 <= hits <= n:
        raise ValueError(f"hits ({hits}) must be within 0..n ({n})")
    phat = hits / n
    denominator = 1.0 + (z * z) / n
    centre = (phat + (z * z) / (2 * n)) / denominator
    margin = (z / denominator) * math.sqrt(phat * (1 - phat) / n + (z * z) / (4 * n * n))
    return max(0.0, centre - margin), min(1.0, centre + margin)


@dataclass(frozen=True)
class CalibrationBucket:
    low: int           # inclusive, percent
    high: int          # exclusive, except the top bucket where it is inclusive
    count: int         # resolved predictions in this bucket
    hits: int          # of those, how many came true
    mean_stated: float | None   # mean stated probability, 0-1
    hit_rate: float | None      # observed fraction true, 0-1
    ci_low: float | None
    ci_high: float | None

    @property
    def label(self) -> str:
        joiner = "-"
        return f"{self.low}{joiner}{self.high}%"

    @property
    def thin(self) -> bool:
        return 0 < self.count < THIN_BUCKET

    @property
    def empty(self) -> bool:
        return self.count == 0


def calibration(predictions: Iterable[Prediction]) -> list[CalibrationBucket]:
    """Bucket resolved predictions by stated confidence and compare stated to observed.

    Every bucket is returned, including empty ones, so the chart shows the gaps in the record
    rather than silently closing them up.
    """
    counts = [0] * BUCKET_COUNT
    hits = [0] * BUCKET_COUNT
    stated_totals = [0.0] * BUCKET_COUNT

    for prediction in scored(predictions):
        if not prediction.resolved:
            continue
        index = bucket_index(prediction.probability)
        counts[index] += 1
        stated_totals[index] += prediction.p
        if prediction.outcome:
            hits[index] += 1

    buckets: list[CalibrationBucket] = []
    for index in range(BUCKET_COUNT):
        low = index * BUCKET_WIDTH
        high = low + BUCKET_WIDTH
        count = counts[index]
        if count == 0:
            buckets.append(
                CalibrationBucket(low, high, 0, 0, None, None, None, None)
            )
            continue
        ci_low, ci_high = wilson_interval(hits[index], count)
        buckets.append(
            CalibrationBucket(
                low=low,
                high=high,
                count=count,
                hits=hits[index],
                mean_stated=stated_totals[index] / count,
                hit_rate=hits[index] / count,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )
    return buckets


@dataclass(frozen=True)
class RollingPoint:
    index: int          # 1-based count of resolved predictions so far
    date: str           # ISO resolution date
    prediction_id: str
    brier_to_date: float


def rolling_brier(predictions: Sequence[Prediction]) -> list[RollingPoint]:
    """Cumulative Brier score after each resolution, in resolution order.

    This is the series that shows whether the record is improving or drifting. It is
    cumulative rather than a fixed window because with a small number of resolutions a
    window is mostly noise.
    """
    resolved = sorted(
        (p for p in scored(predictions) if p.resolved),
        key=lambda p: (p.resolved_at, p.sequence),
    )
    points: list[RollingPoint] = []
    running = 0.0
    for index, prediction in enumerate(resolved, start=1):
        outcome = 1.0 if prediction.outcome else 0.0
        running += (prediction.p - outcome) ** 2
        assert prediction.resolved_at is not None  # guaranteed by model.parse
        points.append(
            RollingPoint(
                index=index,
                date=prediction.resolved_at.isoformat(),
                prediction_id=prediction.id,
                brier_to_date=running / index,
            )
        )
    return points


@dataclass(frozen=True)
class Standing:
    total: int          # real records; example records are excluded throughout
    resolved: int
    open: int
    brier: float | None
    baseline: float
    skill: float | None
    hits: int
    misses: int
    examples: int       # listed on the page, counted in nothing


def standing(predictions: Sequence[Prediction]) -> Standing:
    """The headline numbers. Open predictions are counted, never hidden."""
    real = scored(predictions)
    resolved = [p for p in real if p.resolved]
    brier = brier_score(predictions)
    return Standing(
        total=len(real),
        resolved=len(resolved),
        open=len(real) - len(resolved),
        brier=brier,
        baseline=BASELINE_BRIER,
        skill=skill_score(brier),
        hits=sum(1 for p in resolved if p.outcome),
        misses=sum(1 for p in resolved if not p.outcome),
        examples=len(predictions) - len(real),
    )
