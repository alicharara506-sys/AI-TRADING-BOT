from __future__ import annotations

from datetime import UTC, datetime

import pytest

from analytics.outcome_analytics import (
    MIN_LOSSES_FOR_CALIBRATION,
    MIN_OUTCOMES_IN_A_SCORE_SEGMENT,
    MIN_RESOLVED_FOR_CALIBRATION,
    MIN_WINS_FOR_CALIBRATION,
    FrictionModel,
    OutcomeAnalytics,
)
from core.interfaces.types import Direction
from live_tracking.types import HitTarget, OutcomeStatus, SignalOutcome

_ZERO_FRICTION = FrictionModel(spread_pips=0.0, commission_pips=0.0)

_GENERATED = datetime(2026, 1, 1, tzinfo=UTC)
_RESOLVED = datetime(2026, 1, 1, 1, tzinfo=UTC)


def _outcome(
    *,
    id: str = "o1",
    symbol: str = "XAUUSD",
    final_pips: float | None = 10.0,
    score: float = 0.66,
    regime: str | None = None,
    achieved_rr: float | None = None,
    resolved: bool = True,
) -> SignalOutcome:
    outcome = SignalOutcome(
        id=id,
        symbol=symbol,
        direction=Direction.LONG,
        strategy_name="signal_fusion",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        pip_size=0.1,
        timestamp_generated=_GENERATED,
        score_at_generation=score,
        uncertainty_at_generation="medium",
        regime_at_generation=regime,
    )
    if resolved:
        outcome.status = OutcomeStatus.TP1_HIT if (final_pips or 0) > 0 else OutcomeStatus.SL_HIT
        outcome.hit_target = HitTarget.TP1 if (final_pips or 0) > 0 else HitTarget.SL
        outcome.timestamp_resolved = _RESOLVED
        outcome.final_pips = final_pips
        outcome.achieved_risk_reward = achieved_rr
    return outcome


def test_unresolved_and_open_outcomes_are_excluded() -> None:
    analytics = OutcomeAnalytics(
        [_outcome(id="a", resolved=False), _outcome(id="b", final_pips=None)]
    )

    assert analytics.resolved_count() == 0
    assert analytics.win_rate() is None
    assert analytics.expectancy_pips() is None


def test_friction_model_deducts_spread_and_commission_from_raw_pips() -> None:
    friction = FrictionModel(spread_pips=1.5, commission_pips=0.7)
    assert friction.apply(10.0) == pytest.approx(7.8)


def test_win_rate_uses_net_pips_after_default_friction() -> None:
    # Default friction is 1.5 + 0.7 = 2.2 pips -- a raw +2.0 pip result
    # nets negative and must count as a loss, not a win.
    outcomes = [_outcome(id="a", final_pips=2.0), _outcome(id="b", final_pips=10.0)]
    analytics = OutcomeAnalytics(outcomes)

    assert analytics.win_rate() == pytest.approx(0.5)


def test_win_rate_is_none_with_no_resolved_outcomes() -> None:
    analytics = OutcomeAnalytics([])
    assert analytics.win_rate() is None


def test_expectancy_pips_reuses_analytics_metrics_expectancy() -> None:
    outcomes = [_outcome(id="a", final_pips=20.0), _outcome(id="b", final_pips=-10.0)]
    analytics = OutcomeAnalytics(outcomes, friction=_ZERO_FRICTION)

    # win_rate 0.5, avg_win 20, avg_loss 10 -> 0.5*20 - 0.5*10 = 5.0
    assert analytics.expectancy_pips() == pytest.approx(5.0)


def test_win_rate_by_score_bucket_groups_by_percentage_score() -> None:
    outcomes = [
        _outcome(id="a", score=0.45, final_pips=10.0),
        _outcome(id="b", score=0.48, final_pips=-10.0),
        _outcome(id="c", score=0.75, final_pips=10.0),
    ]
    analytics = OutcomeAnalytics(outcomes, friction=_ZERO_FRICTION)

    buckets = {(b.lower, b.upper): b for b in analytics.win_rate_by_score_bucket()}

    assert buckets[(40.0, 50.0)].sample_count == 2
    assert buckets[(40.0, 50.0)].win_rate == pytest.approx(0.5)
    assert buckets[(70.0, 100.0001)].sample_count == 1
    assert buckets[(70.0, 100.0001)].win_rate == pytest.approx(1.0)


def test_win_rate_by_symbol_and_regime() -> None:
    outcomes = [
        _outcome(id="a", symbol="XAUUSD", regime="trend_up", final_pips=10.0),
        _outcome(id="b", symbol="XAUUSD", regime="trend_up", final_pips=-10.0),
        _outcome(id="c", symbol="EURUSD", regime=None, final_pips=10.0),
    ]
    analytics = OutcomeAnalytics(outcomes, friction=_ZERO_FRICTION)

    by_symbol = analytics.win_rate_by_symbol()
    by_regime = analytics.win_rate_by_regime()

    assert by_symbol["XAUUSD"] == pytest.approx(0.5)
    assert by_symbol["EURUSD"] == pytest.approx(1.0)
    assert by_regime == {"trend_up": pytest.approx(0.5)}


def test_average_planned_and_achieved_risk_reward() -> None:
    outcomes = [
        _outcome(id="a", achieved_rr=2.0),
        _outcome(id="b", achieved_rr=-1.0),
    ]
    analytics = OutcomeAnalytics(outcomes)

    # planned R:R for every fixture is (110-100)/(100-95) == 2.0
    assert analytics.average_planned_risk_reward() == pytest.approx(2.0)
    assert analytics.average_achieved_risk_reward() == pytest.approx(0.5)


def test_rolling_win_rate_is_empty_before_a_full_window() -> None:
    analytics = OutcomeAnalytics([_outcome(id="a"), _outcome(id="b")])
    assert analytics.rolling_win_rate(30) == []


def test_rolling_win_rate_over_a_full_window() -> None:
    outcomes = [_outcome(id=str(i), final_pips=10.0) for i in range(3)]
    analytics = OutcomeAnalytics(outcomes, friction=_ZERO_FRICTION)

    assert analytics.rolling_win_rate(3) == [pytest.approx(1.0)]


def test_is_calibrated_false_below_minimum_resolved_count() -> None:
    outcomes = [_outcome(id=str(i)) for i in range(MIN_RESOLVED_FOR_CALIBRATION - 1)]
    analytics = OutcomeAnalytics(outcomes)
    assert analytics.is_calibrated() is False


def test_is_calibrated_false_without_enough_wins_or_losses() -> None:
    # Enough total resolved outcomes, but every single one nets a loss --
    # zero wins fails the >=40-wins requirement regardless of count.
    outcomes = [
        _outcome(id=str(i), final_pips=-10.0, score=0.75)
        for i in range(MIN_RESOLVED_FOR_CALIBRATION)
    ]
    analytics = OutcomeAnalytics(outcomes)
    assert analytics.is_calibrated() is False


def test_is_calibrated_true_when_every_gate_is_satisfied() -> None:
    wins = [
        _outcome(id=f"w{i}", final_pips=10.0, score=0.75)
        for i in range(max(MIN_WINS_FOR_CALIBRATION, MIN_OUTCOMES_IN_A_SCORE_SEGMENT))
    ]
    losses = [
        _outcome(id=f"l{i}", final_pips=-10.0, score=0.45)
        for i in range(MIN_LOSSES_FOR_CALIBRATION)
    ]
    padding_needed = MIN_RESOLVED_FOR_CALIBRATION - len(wins) - len(losses)
    padding = [
        _outcome(id=f"p{i}", final_pips=10.0, score=0.75) for i in range(max(padding_needed, 0))
    ]
    analytics = OutcomeAnalytics(wins + losses + padding)

    assert analytics.is_calibrated() is True


def test_equity_curve_pips_is_cumulative_net_pips() -> None:
    outcomes = [_outcome(id="a", final_pips=10.0), _outcome(id="b", final_pips=5.0)]
    analytics = OutcomeAnalytics(outcomes, friction=_ZERO_FRICTION)

    assert analytics.equity_curve_pips() == pytest.approx([10.0, 15.0])


def test_report_bundles_every_stat() -> None:
    outcomes = [_outcome(id="a", final_pips=10.0), _outcome(id="b", final_pips=-10.0)]
    analytics = OutcomeAnalytics(outcomes)

    report = analytics.report()

    assert report.resolved_count == 2
    assert report.win_count + report.loss_count == 2
    assert report.is_calibrated is False
