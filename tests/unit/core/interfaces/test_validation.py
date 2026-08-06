from __future__ import annotations

from core.interfaces.validation import CheckResult, ValidationReport


def test_passed_is_true_only_when_every_check_passes() -> None:
    report = ValidationReport(
        strategy_name="sma_crossover",
        checks=(
            CheckResult(name="a", passed=True),
            CheckResult(name="b", passed=True),
        ),
    )

    assert report.passed is True


def test_passed_is_false_when_any_check_fails() -> None:
    report = ValidationReport(
        strategy_name="sma_crossover",
        checks=(
            CheckResult(name="a", passed=True),
            CheckResult(name="b", passed=False),
        ),
    )

    assert report.passed is False


def test_passed_is_true_for_no_checks_at_all() -> None:
    report = ValidationReport(strategy_name="sma_crossover", checks=())

    assert report.passed is True


def test_failure_summary_lists_only_failed_check_names() -> None:
    report = ValidationReport(
        strategy_name="sma_crossover",
        checks=(
            CheckResult(name="walk_forward", passed=False),
            CheckResult(name="monte_carlo_drawdown", passed=True),
            CheckResult(name="look_ahead_bias", passed=False),
        ),
    )

    assert report.failure_summary() == "walk_forward, look_ahead_bias"


def test_failure_summary_reports_none_when_all_pass() -> None:
    report = ValidationReport(
        strategy_name="sma_crossover", checks=(CheckResult(name="a", passed=True),)
    )

    assert report.failure_summary() == "none"
