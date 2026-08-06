from __future__ import annotations

from core.interfaces.types import Direction, Evidence, Symbol, TradeSignal
from core.interfaces.validation import CheckResult, ValidationReport
from machine_learning.ai_assistant.rule_based_reviewer import RuleBasedReviewer


async def test_passing_report_review_mentions_pass_and_every_check() -> None:
    report = ValidationReport(
        strategy_name="steady_strategy",
        checks=(
            CheckResult(
                name="walk_forward",
                passed=True,
                detail={"degradation": 0.0, "max_degradation": 0.5},
            ),
            CheckResult(
                name="monte_carlo_drawdown",
                passed=True,
                detail={"percentile": 0.95, "tail_drawdown": 25.05, "max_drawdown_limit": 30.0},
            ),
            CheckResult(name="look_ahead_bias", passed=True, detail={"bars_checked": 20}),
        ),
    )

    text = await RuleBasedReviewer().review_validation_report(report)

    assert "PASSED" in text
    assert "walk_forward" in text
    assert "monte_carlo_drawdown" in text
    assert "look_ahead_bias" in text
    assert "Recommendation" not in text  # only surfaced when the report fails


async def test_failing_report_review_explains_degradation_and_recommends_against_deploy() -> None:
    report = ValidationReport(
        strategy_name="overfit_strategy",
        checks=(
            CheckResult(
                name="walk_forward",
                passed=False,
                detail={"degradation": 1.81, "max_degradation": 0.5},
            ),
            CheckResult(
                name="monte_carlo_drawdown",
                passed=False,
                detail={"percentile": 0.95, "tail_drawdown": 72.0, "max_drawdown_limit": 30.0},
            ),
            CheckResult(name="look_ahead_bias", passed=True, detail={"bars_checked": 20}),
        ),
    )

    text = await RuleBasedReviewer().review_validation_report(report)

    assert "FAILED" in text
    assert "overfitting" in text.lower()
    assert "181%" in text
    assert "Recommendation" in text
    assert "walk_forward, monte_carlo_drawdown" in text


async def test_walk_forward_with_undefined_degradation_explains_why() -> None:
    report = ValidationReport(
        strategy_name="s",
        checks=(
            CheckResult(
                name="walk_forward",
                passed=True,
                detail={"degradation": None, "max_degradation": 0.5},
            ),
        ),
    )

    text = await RuleBasedReviewer().review_validation_report(report)

    assert "not profitable" in text


async def test_walk_forward_too_few_trades_surfaces_the_reason() -> None:
    report = ValidationReport(
        strategy_name="s",
        checks=(
            CheckResult(
                name="walk_forward",
                passed=False,
                detail={"reason": "fewer than 10 trades; cannot walk-forward split meaningfully"},
            ),
        ),
    )

    text = await RuleBasedReviewer().review_validation_report(report)

    assert "fewer than 10 trades" in text


async def test_look_ahead_failure_flags_the_pipeline_as_untrustworthy() -> None:
    report = ValidationReport(
        strategy_name="s",
        checks=(
            CheckResult(
                name="look_ahead_bias",
                passed=False,
                detail={"index": 5, "reason": "bars processed out of chronological order"},
            ),
        ),
    )

    text = await RuleBasedReviewer().review_validation_report(report)

    assert "untrustworthy" in text
    assert "index 5" in text


async def test_explain_trade_signal_lists_every_contributing_module() -> None:
    signal = TradeSignal(
        symbol=Symbol(name="EURUSD"),
        direction=Direction.LONG,
        combined_confidence=0.87,
        threshold=0.6,
        evidence=(
            Evidence(
                source_module="fibonacci_confluence",
                direction=Direction.LONG,
                confidence=0.9,
                rationale={"fib_ratio": 0.618},
            ),
            Evidence(
                source_module="engulfing_pattern",
                direction=Direction.LONG,
                confidence=0.8,
                rationale={"pattern": "engulfing"},
            ),
        ),
    )

    text = await RuleBasedReviewer().explain_trade_signal(signal)

    assert "EURUSD" in text
    assert "87%" in text
    assert "fibonacci_confluence" in text
    assert "engulfing_pattern" in text


async def test_explain_trade_signal_with_no_evidence() -> None:
    signal = TradeSignal(
        symbol=Symbol(name="EURUSD"),
        direction=Direction.SHORT,
        combined_confidence=0.65,
        threshold=0.6,
        evidence=(),
    )

    text = await RuleBasedReviewer().explain_trade_signal(signal)

    assert "0 contributing module(s)" in text
