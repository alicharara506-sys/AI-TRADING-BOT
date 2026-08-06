from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from analytics import metrics


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    """A backtest/strategy performance summary: the Analytics Engine's
    risk/performance metrics suite, computed once and rendered as
    human-readable text -- the same explain()-style pattern already
    established by SignalRecord and RuleBasedReviewer. The report *is* the
    data; render()/to_dict() are views over it, not a separate source of
    truth that could drift out of sync.
    """

    strategy_name: str
    trade_count: int
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    expectancy: float
    system_quality_number: float
    value_at_risk_95: float
    conditional_value_at_risk_95: float

    @classmethod
    def from_returns(cls, strategy_name: str, returns: Sequence[float]) -> PerformanceReport:
        return cls(
            strategy_name=strategy_name,
            trade_count=len(returns),
            total_return=metrics.total_return(returns),
            max_drawdown=metrics.max_drawdown(returns),
            sharpe_ratio=metrics.sharpe_ratio(returns),
            sortino_ratio=metrics.sortino_ratio(returns),
            calmar_ratio=metrics.calmar_ratio(returns),
            profit_factor=metrics.profit_factor(returns),
            expectancy=metrics.expectancy(returns),
            system_quality_number=metrics.system_quality_number(returns),
            value_at_risk_95=metrics.value_at_risk(returns, confidence=0.95),
            conditional_value_at_risk_95=metrics.conditional_value_at_risk(
                returns, confidence=0.95
            ),
        )

    def render(self) -> str:
        return "\n".join(
            [
                f"Performance report: {self.strategy_name}",
                f"  Trades: {self.trade_count}",
                f"  Total return: {self.total_return:.2f}",
                f"  Max drawdown: {self.max_drawdown:.2f}",
                f"  Sharpe: {self.sharpe_ratio:.2f}  Sortino: {self.sortino_ratio:.2f}  "
                f"Calmar: {self.calmar_ratio:.2f}",
                f"  Profit factor: {self.profit_factor:.2f}  Expectancy: {self.expectancy:.2f}  "
                f"SQN: {self.system_quality_number:.2f}",
                f"  VaR(95%): {self.value_at_risk_95:.2f}  "
                f"CVaR(95%): {self.conditional_value_at_risk_95:.2f}",
            ]
        )

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "strategy_name": self.strategy_name,
            "trade_count": self.trade_count,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "system_quality_number": self.system_quality_number,
            "value_at_risk_95": self.value_at_risk_95,
            "conditional_value_at_risk_95": self.conditional_value_at_risk_95,
        }


__all__ = ["PerformanceReport"]
