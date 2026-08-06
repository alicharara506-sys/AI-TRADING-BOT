from __future__ import annotations

from core.event_bus.bus import EventBus
from core.interfaces.events import AccountStateChanged, BarClosed
from core.interfaces.execution import ExecutionEngine
from core.interfaces.risk import RiskModel, SizingModel
from core.interfaces.strategy import Strategy
from core.interfaces.types import Direction, OrderRequest, OrderSide, OrderType, TradeSignal


class StrategyEngine:
    """Drives one Strategy (simple mode: on_bar callback) off BarClosed events.

    Every TradeSignal the strategy emits passes through the Risk Engine's
    signal-level gate before being sized and submitted as an order -- a second,
    independent check on top of whatever order-level gate the ExecutionEngine
    itself sits behind (e.g. RiskGatedExecutionEngine), matching the
    architecture's requirement that the Risk Engine evaluates both TradeSignals
    and OrderRequests.

    The strategy is hot-swappable via set_strategy(): swapping the active
    Strategy instance does not touch Position/Portfolio state, which lives
    entirely in the Position Manager, not in the strategy object.
    """

    def __init__(
        self,
        strategy: Strategy,
        risk_model: RiskModel,
        sizing_model: SizingModel,
        execution_engine: ExecutionEngine,
        event_bus: EventBus,
    ) -> None:
        self._strategy = strategy
        self._risk_model = risk_model
        self._sizing_model = sizing_model
        self._execution_engine = execution_engine
        self._equity: float | None = None
        self._next_correlation_id = 1
        event_bus.subscribe(BarClosed, self._on_bar)
        event_bus.subscribe(AccountStateChanged, self._on_account_state_changed)

    def set_strategy(self, strategy: Strategy) -> None:
        self._strategy = strategy

    @property
    def strategy(self) -> Strategy:
        return self._strategy

    async def _on_account_state_changed(self, event: AccountStateChanged) -> None:
        self._equity = event.account_state.equity

    async def _on_bar(self, event: BarClosed) -> None:
        if self._equity is None:
            return  # no equity snapshot yet -- can't size a position responsibly

        signal = self._strategy.on_bar(event.bar)
        if signal is None:
            return

        approved = self._risk_model.evaluate_signal(signal)
        if approved is None:
            return

        await self._submit_from_signal(approved)

    async def _submit_from_signal(self, signal: TradeSignal) -> None:
        if signal.direction is Direction.NEUTRAL:
            return
        assert self._equity is not None  # guaranteed by the _on_bar guard above

        volume = self._sizing_model.size(signal, equity=self._equity)
        if volume <= 0:
            return

        request = OrderRequest(
            correlation_id=self._next_id(),
            symbol=signal.symbol,
            side=OrderSide.BUY if signal.direction is Direction.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            volume=volume,
        )
        await self._execution_engine.submit_order(request)

    def _next_id(self) -> str:
        correlation_id = f"strategy-{self._next_correlation_id}"
        self._next_correlation_id += 1
        return correlation_id


__all__ = ["StrategyEngine"]
