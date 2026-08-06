from __future__ import annotations

from core.interfaces.types import TradeSignal
from core.interfaces.validation import CheckResult, ValidationReport


class RuleBasedReviewer:
    """Deterministic reference implementation of AIReviewer: every sentence it
    produces is derived directly from CheckResult.detail / Evidence data
    already computed by the Validation Pipeline / Signal Fusion, not an
    independent judgment. A real LLM-backed reviewer is a drop-in replacement
    behind the same Protocol -- this is the honest baseline until one exists,
    not a stand-in pretending to be more than it is.
    """

    def review_validation_report(self, report: ValidationReport) -> str:
        lines = [
            f"Validation review for '{report.strategy_name}': "
            f"{'PASSED' if report.passed else 'FAILED'}."
        ]
        lines.extend(self._explain_check(check) for check in report.checks)
        if not report.passed:
            lines.append(
                "Recommendation: do not deploy to live trading until every check "
                f"passes. Failing checks: {report.failure_summary()}."
            )
        return "\n".join(lines)

    def _explain_check(self, check: CheckResult) -> str:
        status = "passed" if check.passed else "FAILED"
        if check.name == "walk_forward":
            return self._explain_walk_forward(check, status)
        if check.name == "monte_carlo_drawdown":
            return self._explain_monte_carlo(check, status)
        if check.name == "look_ahead_bias":
            return self._explain_look_ahead(check, status)
        return f"- {check.name} {status}: {check.detail}"

    def _explain_walk_forward(self, check: CheckResult, status: str) -> str:
        degradation = check.detail.get("degradation")
        if degradation is None:
            reason = check.detail.get("reason")
            if reason:
                return f"- walk_forward {status}: {reason}."
            return (
                f"- walk_forward {status}: in-sample half was not profitable; "
                "nothing to degrade from."
            )
        max_degradation = check.detail.get("max_degradation", 0.0)
        line = (
            f"- walk_forward {status}: out-of-sample return degraded "
            f"{degradation:.0%} relative to in-sample (limit {max_degradation:.0%})."
        )
        if not check.passed:
            line += (
                " This is a classic overfitting signature: the strategy's apparent "
                "edge did not survive out-of-sample data."
            )
        return line

    def _explain_monte_carlo(self, check: CheckResult, status: str) -> str:
        if "reason" in check.detail:
            return f"- monte_carlo_drawdown {status}: {check.detail['reason']}."
        percentile = check.detail.get("percentile", 0.0)
        tail_drawdown = check.detail.get("tail_drawdown", 0.0)
        limit = check.detail.get("max_drawdown_limit", 0.0)
        return (
            f"- monte_carlo_drawdown {status}: {percentile:.0%}-percentile bootstrapped "
            f"drawdown was {tail_drawdown:.2f} against a limit of {limit:.2f}."
        )

    def _explain_look_ahead(self, check: CheckResult, status: str) -> str:
        if not check.passed:
            index = check.detail.get("index")
            return (
                f"- look_ahead_bias {status}: bars were processed out of chronological "
                f"order at index {index} -- the backtest pipeline itself is untrustworthy "
                "until this is fixed."
            )
        bars_checked = check.detail.get("bars_checked", 0)
        return f"- look_ahead_bias {status}: {bars_checked} bars verified in chronological order."

    def explain_trade_signal(self, signal: TradeSignal) -> str:
        lines = [
            f"{signal.direction.value.upper()} signal for {signal.symbol.canonical} at "
            f"{signal.combined_confidence:.0%} combined confidence "
            f"(threshold {signal.threshold:.0%}), backed by {len(signal.evidence)} "
            "contributing module(s):"
        ]
        for item in signal.evidence:
            lines.append(
                f"- {item.source_module}: {item.direction.value} at "
                f"{item.confidence:.0%} confidence ({item.rationale})"
            )
        return "\n".join(lines)


__all__ = ["RuleBasedReviewer"]
