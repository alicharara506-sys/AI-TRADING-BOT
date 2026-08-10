from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from analytics import metrics
from analytics.rolling import compute_rolling_metric
from live_tracking.types import SignalOutcome

# Every stat in this module is computed on *net* pips: a fixed cost is
# deducted from each resolved outcome's raw final_pips before anything else
# is computed, so win rate/expectancy reflect what an account would
# actually keep, not a frictionless price move. Defaults are deliberately
# conservative placeholders, not measured broker figures (this platform has
# no live commission/spread feed to measure from) -- 1.5 pips is a typical
# major-pair spread; 0.7 pips approximates a $7 round-turn commission under
# the common ~$10-per-pip-per-standard-lot convention. Both are overridable
# per FrictionModel instance.
DEFAULT_SPREAD_FRICTION_PIPS = 1.5
DEFAULT_COMMISSION_FRICTION_PIPS = 0.7

# "Historical probability is unavailable until at least 200 independently
# resolved eligible outcomes exist, including at least 40 wins, 40 losses,
# and 30 outcomes in a score segment" -- the calibration gate already
# documented for the (currently null) historical win probability field
# elsewhere in this platform. "30 outcomes in a score segment" (singular)
# is read literally here as *at least one* segment reaching 30, not every
# segment -- a new, sparsely-populated score bucket should not by itself
# block calibration the other three conditions already support.
MIN_RESOLVED_FOR_CALIBRATION = 200
MIN_WINS_FOR_CALIBRATION = 40
MIN_LOSSES_FOR_CALIBRATION = 40
MIN_OUTCOMES_IN_A_SCORE_SEGMENT = 30

# Score buckets on the familiar 0-100 percentage scale (score_at_generation
# is stored as a 0-1 fraction, the same scale as DecisionReport.confidence).
DEFAULT_SCORE_BUCKET_EDGES_PCT: tuple[float, ...] = (0.0, 40.0, 50.0, 60.0, 70.0, 100.0001)


@dataclass(frozen=True, slots=True)
class FrictionModel:
    spread_pips: float = DEFAULT_SPREAD_FRICTION_PIPS
    commission_pips: float = DEFAULT_COMMISSION_FRICTION_PIPS

    def apply(self, raw_pips: float) -> float:
        return raw_pips - self.spread_pips - self.commission_pips


_DEFAULT_FRICTION_MODEL = FrictionModel()


@dataclass(frozen=True, slots=True)
class ScoreBucketStats:
    lower: float
    upper: float
    win_rate: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class OutcomeReport:
    """A one-shot snapshot of every stat OutcomeAnalytics can compute --
    the same "report is the data" pattern PerformanceReport already uses,
    so a caller (the dashboard) can render one object instead of calling
    many methods."""

    resolved_count: int
    win_count: int
    loss_count: int
    win_rate: float | None
    expectancy_pips: float | None
    average_planned_risk_reward: float | None
    average_achieved_risk_reward: float | None
    score_buckets: tuple[ScoreBucketStats, ...]
    win_rate_by_symbol: dict[str, float]
    win_rate_by_regime: dict[str, float]
    rolling_win_rate_30: list[float]
    rolling_win_rate_100: list[float]
    is_calibrated: bool


class OutcomeAnalytics:
    """Computes real, friction-adjusted performance statistics from
    SignalLifecycleTracker's resolved SignalOutcome history: win rate
    sliced by score bucket / symbol / regime, expectancy, planned-vs-
    achieved R:R, rolling windows, and the same "not enough history yet"
    calibration gate this platform already documents for historical win
    probability (decision_engine's uncertainty field exists precisely
    because that gate isn't met yet -- this class is what would finally
    let it be met, honestly, from real resolved trades).

    Reuses analytics/metrics.py and analytics/rolling.py rather than
    reimplementing expectancy/rolling-window logic -- the exact same
    functions PerformanceReport already builds on, just fed net pips
    instead of account-currency P&L.
    """

    def __init__(
        self,
        outcomes: Sequence[SignalOutcome],
        *,
        friction: FrictionModel = _DEFAULT_FRICTION_MODEL,
    ) -> None:
        self._friction = friction
        self._resolved = [
            outcome
            for outcome in outcomes
            if outcome.timestamp_resolved is not None and outcome.final_pips is not None
        ]

    def _net_pips(self, outcome: SignalOutcome) -> float:
        assert outcome.final_pips is not None
        return self._friction.apply(outcome.final_pips)

    def _net_pips_series(self, outcomes: Sequence[SignalOutcome] | None = None) -> list[float]:
        return [self._net_pips(outcome) for outcome in (outcomes or self._resolved)]

    def resolved_count(self) -> int:
        return len(self._resolved)

    def win_rate(self, outcomes: Sequence[SignalOutcome] | None = None) -> float | None:
        pool = outcomes if outcomes is not None else self._resolved
        if not pool:
            return None
        wins = sum(1 for outcome in pool if self._net_pips(outcome) > 0)
        return wins / len(pool)

    def expectancy_pips(self) -> float | None:
        if not self._resolved:
            return None
        return metrics.expectancy(self._net_pips_series())

    def equity_curve_pips(self) -> list[float]:
        if not self._resolved:
            return []
        return metrics.equity_curve(self._net_pips_series())

    def average_planned_risk_reward(self) -> float | None:
        values = [
            outcome.planned_risk_reward
            for outcome in self._resolved
            if outcome.planned_risk_reward is not None
        ]
        return sum(values) / len(values) if values else None

    def average_achieved_risk_reward(self) -> float | None:
        values = [
            outcome.achieved_risk_reward
            for outcome in self._resolved
            if outcome.achieved_risk_reward is not None
        ]
        return sum(values) / len(values) if values else None

    def win_rate_by_score_bucket(
        self, edges: Sequence[float] = DEFAULT_SCORE_BUCKET_EDGES_PCT
    ) -> tuple[ScoreBucketStats, ...]:
        if len(edges) < 2:
            raise ValueError("edges must have at least a lower and an upper bound")
        buckets: list[ScoreBucketStats] = []
        for lower, upper in zip(edges, edges[1:], strict=False):
            in_bucket = [
                outcome
                for outcome in self._resolved
                if lower <= outcome.score_at_generation * 100.0 < upper
            ]
            win_rate = self.win_rate(in_bucket)
            if win_rate is not None:
                buckets.append(
                    ScoreBucketStats(
                        lower=lower, upper=upper, win_rate=win_rate, sample_count=len(in_bucket)
                    )
                )
        return tuple(buckets)

    def win_rate_by_symbol(self) -> dict[str, float]:
        grouped: dict[str, list[SignalOutcome]] = defaultdict(list)
        for outcome in self._resolved:
            grouped[outcome.symbol].append(outcome)
        return {
            symbol: rate
            for symbol, outcomes in grouped.items()
            if (rate := self.win_rate(outcomes)) is not None
        }

    def win_rate_by_regime(self) -> dict[str, float]:
        grouped: dict[str, list[SignalOutcome]] = defaultdict(list)
        for outcome in self._resolved:
            if outcome.regime_at_generation is not None:
                grouped[outcome.regime_at_generation].append(outcome)
        return {
            regime: rate
            for regime, outcomes in grouped.items()
            if (rate := self.win_rate(outcomes)) is not None
        }

    def rolling_win_rate(self, window: int) -> list[float]:
        series = self._net_pips_series()
        return compute_rolling_metric(
            series,
            window=window,
            metric_fn=lambda values: sum(1 for value in values if value > 0) / len(values),
        )

    def is_calibrated(self) -> bool:
        if len(self._resolved) < MIN_RESOLVED_FOR_CALIBRATION:
            return False
        wins = sum(1 for outcome in self._resolved if self._net_pips(outcome) > 0)
        losses = len(self._resolved) - wins
        if wins < MIN_WINS_FOR_CALIBRATION or losses < MIN_LOSSES_FOR_CALIBRATION:
            return False
        buckets = self.win_rate_by_score_bucket()
        return any(bucket.sample_count >= MIN_OUTCOMES_IN_A_SCORE_SEGMENT for bucket in buckets)

    def report(self) -> OutcomeReport:
        wins = sum(1 for outcome in self._resolved if self._net_pips(outcome) > 0)
        return OutcomeReport(
            resolved_count=len(self._resolved),
            win_count=wins,
            loss_count=len(self._resolved) - wins,
            win_rate=self.win_rate(),
            expectancy_pips=self.expectancy_pips(),
            average_planned_risk_reward=self.average_planned_risk_reward(),
            average_achieved_risk_reward=self.average_achieved_risk_reward(),
            score_buckets=self.win_rate_by_score_bucket(),
            win_rate_by_symbol=self.win_rate_by_symbol(),
            win_rate_by_regime=self.win_rate_by_regime(),
            rolling_win_rate_30=self.rolling_win_rate(30),
            rolling_win_rate_100=self.rolling_win_rate(100),
            is_calibrated=self.is_calibrated(),
        )


__all__ = [
    "DEFAULT_COMMISSION_FRICTION_PIPS",
    "DEFAULT_SCORE_BUCKET_EDGES_PCT",
    "DEFAULT_SPREAD_FRICTION_PIPS",
    "MIN_LOSSES_FOR_CALIBRATION",
    "MIN_OUTCOMES_IN_A_SCORE_SEGMENT",
    "MIN_RESOLVED_FOR_CALIBRATION",
    "MIN_WINS_FOR_CALIBRATION",
    "FrictionModel",
    "OutcomeAnalytics",
    "OutcomeReport",
    "ScoreBucketStats",
]
