from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def _as_array(returns: Sequence[float]) -> np.ndarray:
    if len(returns) == 0:
        raise ValueError("returns must not be empty")
    return np.asarray(returns, dtype=float)


def total_return(returns: Sequence[float]) -> float:
    return float(_as_array(returns).sum())


def equity_curve(returns: Sequence[float]) -> list[float]:
    return list(np.cumsum(_as_array(returns)))


def max_drawdown(returns: Sequence[float]) -> float:
    """The largest peak-to-trough decline in the equity curve, as a positive
    number (0.0 for a curve that never dips below its running peak)."""
    curve = np.cumsum(_as_array(returns))
    running_max = np.maximum.accumulate(curve)
    drawdown = running_max - curve
    return float(drawdown.max())


def sharpe_ratio(
    returns: Sequence[float], *, risk_free_rate: float = 0.0, periods_per_year: float = 1.0
) -> float:
    """(mean excess return / return std), annualized by sqrt(periods_per_year).
    0.0 when returns have no variance (nothing to divide by)."""
    array = _as_array(returns)
    excess = array - risk_free_rate
    std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
    if std == 0.0:
        return 0.0
    return float(excess.mean() / std * math.sqrt(periods_per_year))


def sortino_ratio(
    returns: Sequence[float], *, risk_free_rate: float = 0.0, periods_per_year: float = 1.0
) -> float:
    """Like Sharpe, but only penalizes downside deviation (returns below the
    risk-free rate) -- upside volatility isn't treated as risk."""
    array = _as_array(returns)
    excess = array - risk_free_rate
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.sqrt((downside**2).mean()))
    if downside_std == 0.0:
        return 0.0
    return float(excess.mean() / downside_std * math.sqrt(periods_per_year))


def calmar_ratio(returns: Sequence[float], *, periods_per_year: float = 1.0) -> float:
    """Annualized return divided by max drawdown. 0.0 when there is no
    drawdown to divide by (a curve that never dipped below its peak)."""
    array = _as_array(returns)
    drawdown = max_drawdown(returns)
    if drawdown == 0.0:
        return 0.0
    annualized_return = float(array.mean()) * periods_per_year
    return annualized_return / drawdown


def profit_factor(returns: Sequence[float]) -> float:
    """Gross profit / gross loss. inf when there are no losing trades at all
    (and at least one winning trade); 0.0 when there are no winning trades."""
    array = _as_array(returns)
    gross_profit = float(array[array > 0].sum())
    gross_loss = float(-array[array < 0].sum())
    if gross_loss == 0.0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def expectancy(returns: Sequence[float]) -> float:
    """Average expected profit per trade: (win_rate * avg_win) -
    (loss_rate * avg_loss). Equivalent to mean(returns), computed via the
    textbook win/loss decomposition rather than a shortcut straight to the
    mean, so the win-rate and average-win/loss components are visible to
    anyone reading the formula."""
    array = _as_array(returns)
    wins = array[array > 0]
    losses = array[array < 0]
    n = len(array)
    win_rate = len(wins) / n
    loss_rate = len(losses) / n
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0
    return win_rate * avg_win - loss_rate * avg_loss


def system_quality_number(returns: Sequence[float]) -> float:
    """SQN = sqrt(n) * mean(returns) / std(returns). 0.0 when returns have no
    variance."""
    array = _as_array(returns)
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    if std == 0.0:
        return 0.0
    return float(math.sqrt(len(array)) * array.mean() / std)


def value_at_risk(returns: Sequence[float], *, confidence: float = 0.95) -> float:
    """Historical (empirical) VaR: the loss threshold not exceeded with
    probability `confidence`, as a positive number."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    array = _as_array(returns)
    return float(-np.quantile(array, 1.0 - confidence))


def conditional_value_at_risk(returns: Sequence[float], *, confidence: float = 0.95) -> float:
    """Expected Shortfall: the average loss in the worst (1 - confidence)
    tail of outcomes, as a positive number."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    array = _as_array(returns)
    threshold = np.quantile(array, 1.0 - confidence)
    tail = array[array <= threshold]
    if len(tail) == 0:
        tail = np.array([threshold])
    return float(-tail.mean())


__all__ = [
    "calmar_ratio",
    "conditional_value_at_risk",
    "equity_curve",
    "expectancy",
    "max_drawdown",
    "profit_factor",
    "sharpe_ratio",
    "sortino_ratio",
    "system_quality_number",
    "total_return",
    "value_at_risk",
]
