from __future__ import annotations

from collections.abc import Callable, Sequence

from backtesting.validation.pipeline import ValidationPipeline
from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.execution.order import Order
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.interfaces.events import AccountStateChanged, BarClosed, TickReceived
from core.interfaces.risk import SizingModel
from core.interfaces.strategy import Strategy
from core.interfaces.types import AccountState, Bar, OrderSide, OrderStatus, Tick
from core.interfaces.validation import ValidationReport
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine
from core.strategy.engine import StrategyEngine
from execution_backends.backtest.engine import BacktestExecutionEngine

_MIN_BARS = 2
# Preflight only publishes one AccountStateChanged, before any bar is
# replayed -- RiskEngine's daily-loss check re-evaluates solely inside that
# handler, so it can never trip mid-replay regardless of this value. A large
# constant avoids the >0 validation failing for a starting_equity of 0.
_PREFLIGHT_DAILY_LOSS_LIMIT = 1_000_000_000.0


def pair_round_trip_returns(orders: Sequence[Order]) -> list[float]:
    """Pairs each consecutive filled order into one round-trip trade return.

    Correct for a strategy that holds at most one net position and flips it
    with an opposite-side order of matching volume (e.g. SmaCrossoverStrategy):
    order i opens a position that order i+1 exactly closes (and, if its
    direction differs, simultaneously reopens in the new direction) -- the
    same equal-volume-closes-rather-than-reduces assumption
    core/portfolio/position_manager.py already makes. Orders that never got
    filled (rejected, still pending) are ignored; a dangling final order that
    hasn't been closed by anything yet contributes no return.
    """
    filled = [
        order
        for order in orders
        if order.status is OrderStatus.FILLED and order.fill_price is not None
    ]
    returns: list[float] = []
    for opening, closing in zip(filled, filled[1:], strict=False):
        assert opening.fill_price is not None
        assert closing.fill_price is not None
        volume = opening.request.volume
        if opening.request.side is OrderSide.BUY:
            pnl = (closing.fill_price - opening.fill_price) * volume
        else:
            pnl = (opening.fill_price - closing.fill_price) * volume
        returns.append(pnl)
    return returns


async def run_preflight_backtest(
    strategy_factory: Callable[[], Strategy],
    bars: Sequence[Bar],
    *,
    strategy_name: str,
    starting_equity: float,
    sizing_model: SizingModel,
    pipeline: ValidationPipeline,
    max_open_positions: int = 2,
    spread: float = 0.0002,
) -> tuple[ValidationReport, list[float]]:
    """Replays real historical bars (fetched from the live connector) through
    the same Strategy/Risk/Sizing/BacktestExecutionEngine wiring
    docs/runbook/backtest-to-live.md's step 2 describes, then runs the
    resulting trade returns through the Validation Pipeline. This is the gate
    LiveRunner.run_forever() calls before it will construct a single live
    order path -- a strategy that doesn't pass here never reaches the venue.

    max_open_positions defaults to 2, not 1: a flip-only strategy's *closing*
    order is evaluated by RiskEngine.evaluate_signal while the position it is
    about to close is still open, so a limit of 1 would veto every flip after
    the first trade. This mirrors the same constraint LiveRunner applies to
    the live Risk Engine for the identical reason.
    """
    if len(bars) < _MIN_BARS:
        raise ValueError(f"Need at least {_MIN_BARS} historical bars, got {len(bars)}")

    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)
    risk_engine = RiskEngine(
        portfolio,
        event_bus,
        max_open_positions=max_open_positions,
        daily_loss_limit=_PREFLIGHT_DAILY_LOSS_LIMIT,
    )
    execution_engine = BacktestExecutionEngine(event_bus)
    gated_engine = RiskGatedExecutionEngine(execution_engine, risk_engine, event_bus)
    strategy = strategy_factory()
    StrategyEngine(strategy, risk_engine, sizing_model, gated_engine, event_bus)

    await event_bus.publish(
        AccountStateChanged(
            account_state=AccountState(
                balance=starting_equity,
                equity=starting_equity,
                margin=0.0,
                free_margin=starting_equity,
                margin_level=None,
                currency="USD",
            )
        )
    )

    for bar in bars:
        tick = Tick(
            symbol=bar.symbol,
            timestamp=bar.timestamp,
            bid=bar.close - spread / 2,
            ask=bar.close + spread / 2,
        )
        await event_bus.publish(TickReceived(tick=tick))
        await event_bus.publish(BarClosed(bar=bar))

    trade_returns = pair_round_trip_returns(order_manager.list_orders())
    bar_timestamps = [bar.timestamp for bar in bars]
    report = pipeline.run(
        strategy_name=strategy_name, trade_returns=trade_returns, bar_timestamps=bar_timestamps
    )
    return report, trade_returns


__all__ = ["pair_round_trip_returns", "run_preflight_backtest"]
