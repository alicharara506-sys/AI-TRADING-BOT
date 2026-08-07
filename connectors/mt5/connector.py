from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

from connectors.mt5.api import (
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING,
    DEAL_ENTRY_IN,
    DEAL_ENTRY_OUT,
    ORDER_TYPE_BUY,
    ORDER_TYPE_SELL,
    TIMEFRAME_MAP,
    TRADE_ACTION_DEAL,
    TRADE_ACTION_SLTP,
    TRADE_RETCODE_DONE,
    MT5Api,
)
from connectors.mt_common.reconnect import ReconnectPolicy
from connectors.mt_common.symbols import SymbolMapper
from core.event_bus.bus import EventBus
from core.interfaces.clock import Clock
from core.interfaces.events import BarClosed, ConnectionStateChanged, TickReceived
from core.interfaces.types import (
    AccountMode,
    AccountState,
    Bar,
    ConnectionState,
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Symbol,
    SymbolInfo,
    Tick,
    Timeframe,
    Trade,
)
from core.kernel.clock import LiveClock

T = TypeVar("T")


def _field(row: Any, name: str) -> Any:
    """copy_rates_from_pos returns numpy structured-array rows (dict-style field
    access); test doubles use plain dicts. Both are handled the same way."""
    try:
        return row[name]
    except (TypeError, KeyError, IndexError):
        return getattr(row, name)


class MT5Connector:
    """Connector Protocol implementation for MetaTrader 5, driven by an injected
    MT5Api (the real `MetaTrader5` module in production, a fake in tests)."""

    def __init__(
        self,
        api: MT5Api,
        event_bus: EventBus,
        *,
        login: int,
        password: str,
        server: str,
        symbol_mapper: SymbolMapper | None = None,
        clock: Clock | None = None,
        poll_interval: float = 1.0,
        reconnect_policy: ReconnectPolicy | None = None,
    ) -> None:
        self._api = api
        self._event_bus = event_bus
        self._login = login
        self._password = password
        self._server = server
        self._symbol_mapper = symbol_mapper or SymbolMapper()
        self._clock = clock or LiveClock()
        self._poll_interval = poll_interval
        self._reconnect_policy = reconnect_policy or ReconnectPolicy()
        self._connected = False
        self._tick_subscriptions: set[str] = set()
        self._bar_subscriptions: set[tuple[str, Timeframe]] = set()
        self._last_tick_time: dict[str, float] = {}
        self._last_bar_time: dict[tuple[str, Timeframe], float] = {}
        self._poll_task: asyncio.Task[None] | None = None

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        if not self._api.initialize():
            code, message = self._api.last_error()
            raise ConnectionError(f"MT5 initialize failed ({code}): {message}")
        if not self._api.login(self._login, password=self._password, server=self._server):
            code, message = self._api.last_error()
            raise ConnectionError(f"MT5 login failed ({code}): {message}")
        self._connected = True
        await self._event_bus.publish(ConnectionStateChanged(state=ConnectionState.CONNECTED))

    async def disconnect(self) -> None:
        self._api.shutdown()
        self._connected = False
        await self._event_bus.publish(ConnectionStateChanged(state=ConnectionState.DISCONNECTED))

    def is_connected(self) -> bool:
        return self._connected

    async def _mark_disconnected(self) -> None:
        """Any direct MT5Api call that raises means the terminal connection is
        no longer trustworthy -- flip state and tell the rest of the system,
        rather than leaving `_connected` stale while an order/query path fails
        silently underneath it. Deliberately does not auto-retry the call:
        blindly retrying order_send risks submitting a duplicate order.
        """
        if self._connected:
            self._connected = False
            await self._event_bus.publish(ConnectionStateChanged(state=ConnectionState.LOST))

    async def _call(self, func: Callable[[], T]) -> T:
        try:
            return func()
        except Exception:
            await self._mark_disconnected()
            raise

    async def start(self) -> None:
        await self.connect()
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self.disconnect()

    # -- subscriptions ---------------------------------------------------------

    async def subscribe_ticks(self, symbol: Symbol) -> None:
        broker_symbol = self._symbol_mapper.to_broker(symbol)
        await self._call(lambda: self._api.symbol_select(broker_symbol, True))
        self._tick_subscriptions.add(broker_symbol)

    async def subscribe_bars(self, symbol: Symbol, timeframe: Timeframe) -> None:
        broker_symbol = self._symbol_mapper.to_broker(symbol)
        await self._call(lambda: self._api.symbol_select(broker_symbol, True))
        self._bar_subscriptions.add((broker_symbol, timeframe))

    # -- queries -----------------------------------------------------------

    async def get_symbol_info(self, symbol: Symbol) -> SymbolInfo:
        broker_symbol = self._symbol_mapper.to_broker(symbol)
        # The real terminal only returns data for symbols visible in Market
        # Watch; symbol_select() adds it if it isn't there yet. Best-effort --
        # a False return still falls through to the symbol_info() None check.
        await self._call(lambda: self._api.symbol_select(broker_symbol, True))
        info = await self._call(lambda: self._api.symbol_info(broker_symbol))
        if info is None:
            raise LookupError(f"Unknown symbol '{broker_symbol}'")

        account = await self._call(self._api.account_info)
        margin_mode = getattr(account, "margin_mode", ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
        account_mode = (
            AccountMode.HEDGING
            if margin_mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING
            else AccountMode.NETTING
        )

        return SymbolInfo(
            symbol=symbol,
            digits=info.digits,
            point=info.point,
            contract_size=info.trade_contract_size,
            min_volume=info.volume_min,
            max_volume=info.volume_max,
            volume_step=info.volume_step,
            account_mode=account_mode,
        )

    async def get_historical_bars(
        self, symbol: Symbol, timeframe: Timeframe, count: int
    ) -> list[Bar]:
        """Fetch up to `count` fully-closed historical bars, oldest first.
        start_pos=1 skips the still-forming current bar (position 0) that
        _poll_bars deliberately also treats as not-yet-closed -- used by the
        live-trading pre-flight backtest (live_trading/preflight.py) to
        validate a strategy against this account's own real history before
        it may place a single live order.
        """
        broker_symbol = self._symbol_mapper.to_broker(symbol)
        await self._call(lambda: self._api.symbol_select(broker_symbol, True))
        rows = await self._call(
            lambda: self._api.copy_rates_from_pos(
                broker_symbol, TIMEFRAME_MAP[timeframe.value], 1, count
            )
        )
        if rows is None:
            return []
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(_field(row, "time"), tz=UTC),
                open=_field(row, "open"),
                high=_field(row, "high"),
                low=_field(row, "low"),
                close=_field(row, "close"),
                volume=_field(row, "tick_volume"),
            )
            for row in rows
        ]

    async def get_trade_history(self, from_ts: datetime, to_ts: datetime) -> list[Trade]:
        deals = await self._call(lambda: self._api.history_deals_get(from_ts, to_ts) or ())
        return self._pair_deals_into_trades(deals)

    def _pair_deals_into_trades(self, deals: Sequence[Any]) -> list[Trade]:
        open_deals: dict[int, Any] = {}
        trades: list[Trade] = []
        for deal in deals:
            entry = getattr(deal, "entry", DEAL_ENTRY_IN)
            if entry == DEAL_ENTRY_IN:
                open_deals[deal.position_id] = deal
            elif entry == DEAL_ENTRY_OUT:
                open_deal = open_deals.pop(deal.position_id, None)
                if open_deal is None:
                    continue
                trades.append(
                    Trade(
                        trade_id=str(deal.position_id),
                        symbol=self._symbol_mapper.from_broker(deal.symbol),
                        side=OrderSide.BUY if open_deal.type == ORDER_TYPE_BUY else OrderSide.SELL,
                        volume=deal.volume,
                        open_price=open_deal.price,
                        close_price=deal.price,
                        open_time=datetime.fromtimestamp(open_deal.time, tz=UTC),
                        close_time=datetime.fromtimestamp(deal.time, tz=UTC),
                        profit=deal.profit,
                    )
                )
        return trades

    async def get_open_positions(self) -> list[Position]:
        positions = await self._call(lambda: self._api.positions_get() or ())
        return [
            Position(
                position_id=str(p.ticket),
                symbol=self._symbol_mapper.from_broker(p.symbol),
                side=OrderSide.BUY if p.type == ORDER_TYPE_BUY else OrderSide.SELL,
                volume=p.volume,
                open_price=p.price_open,
                stop_loss=p.sl or None,
                take_profit=p.tp or None,
            )
            for p in positions
        ]

    async def get_account_state(self) -> AccountState:
        account = await self._call(self._api.account_info)
        if account is None:
            raise ConnectionError("account_info() returned None; not connected?")
        return AccountState(
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.margin_free,
            margin_level=account.margin_level or None,
            currency=account.currency,
        )

    # -- orders -----------------------------------------------------------

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        if request.order_type is not OrderType.MARKET:
            raise NotImplementedError(
                f"MT5Connector currently only submits market orders, got {request.order_type}"
            )
        broker_symbol = self._symbol_mapper.to_broker(request.symbol)
        mt5_request: dict[str, Any] = {
            "action": TRADE_ACTION_DEAL,
            "symbol": broker_symbol,
            "volume": request.volume,
            "type": ORDER_TYPE_BUY if request.side is OrderSide.BUY else ORDER_TYPE_SELL,
            "comment": request.correlation_id,
        }
        if request.price is not None:
            mt5_request["price"] = request.price
        if request.stop_loss is not None:
            mt5_request["sl"] = request.stop_loss
        if request.take_profit is not None:
            mt5_request["tp"] = request.take_profit

        result = await self._call(lambda: self._api.order_send(mt5_request))
        if result is None or result.retcode != TRADE_RETCODE_DONE:
            code = getattr(result, "retcode", None)
            reason = getattr(result, "comment", "order_send returned no result")
            return OrderAck(
                correlation_id=request.correlation_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                reason=f"{code}: {reason}",
            )
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id=str(result.order),
            status=OrderStatus.FILLED,
            fill_price=getattr(result, "price", None),
        )

    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        position = await self._find_position(position_id)
        request = {
            "action": TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": stop_loss if stop_loss is not None else position.sl,
            "tp": take_profit if take_profit is not None else position.tp,
        }
        result = await self._call(lambda: self._api.order_send(request))
        if result is None or result.retcode != TRADE_RETCODE_DONE:
            raise RuntimeError(f"Failed to modify position '{position_id}'")

    async def close_position(self, position_id: str, *, volume: float | None = None) -> None:
        position = await self._find_position(position_id)
        close_side = ORDER_TYPE_SELL if position.type == ORDER_TYPE_BUY else ORDER_TYPE_BUY
        request = {
            "action": TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": volume if volume is not None else position.volume,
            "type": close_side,
            "position": position.ticket,
        }
        result = await self._call(lambda: self._api.order_send(request))
        if result is None or result.retcode != TRADE_RETCODE_DONE:
            raise RuntimeError(f"Failed to close position '{position_id}'")

    async def _find_position(self, position_id: str) -> Any:
        positions = await self._call(lambda: self._api.positions_get() or ())
        for position in positions:
            if str(position.ticket) == position_id:
                return position
        raise LookupError(f"Unknown position '{position_id}'")

    # -- polling loop (tick/bar streaming, reconnect on failure) ------------

    async def _poll_loop(self) -> None:
        attempt = 0
        while True:
            try:
                await self.poll_once()
                attempt = 0
            except Exception:  # noqa: BLE001 - connection loss triggers reconnect below
                self._connected = False
                await self._event_bus.publish(
                    ConnectionStateChanged(state=ConnectionState.LOST)
                )
                attempt += 1
                await asyncio.sleep(self._reconnect_policy.delay_for_attempt(attempt))
                with contextlib.suppress(Exception):
                    await self.connect()
                continue
            await asyncio.sleep(self._poll_interval)

    async def poll_once(self) -> None:
        await self._poll_ticks()
        await self._poll_bars()

    async def _poll_ticks(self) -> None:
        for broker_symbol in list(self._tick_subscriptions):
            tick = self._api.symbol_info_tick(broker_symbol)
            if tick is None:
                continue
            if self._last_tick_time.get(broker_symbol) == tick.time:
                continue
            self._last_tick_time[broker_symbol] = tick.time
            await self._event_bus.publish(
                TickReceived(
                    tick=Tick(
                        symbol=self._symbol_mapper.from_broker(broker_symbol),
                        timestamp=datetime.fromtimestamp(tick.time, tz=UTC),
                        bid=tick.bid,
                        ask=tick.ask,
                        volume=getattr(tick, "volume", 0.0),
                    )
                )
            )

    async def _poll_bars(self) -> None:
        for broker_symbol, timeframe in list(self._bar_subscriptions):
            rates = self._api.copy_rates_from_pos(
                broker_symbol, TIMEFRAME_MAP[timeframe.value], 0, 1
            )
            if rates is None or len(rates) == 0:
                continue
            row = rates[0]
            row_time = _field(row, "time")
            key = (broker_symbol, timeframe)
            if self._last_bar_time.get(key) == row_time:
                continue
            self._last_bar_time[key] = row_time
            await self._event_bus.publish(
                BarClosed(
                    bar=Bar(
                        symbol=self._symbol_mapper.from_broker(broker_symbol),
                        timeframe=timeframe,
                        timestamp=datetime.fromtimestamp(row_time, tz=UTC),
                        open=_field(row, "open"),
                        high=_field(row, "high"),
                        low=_field(row, "low"),
                        close=_field(row, "close"),
                        volume=_field(row, "tick_volume"),
                    )
                )
            )


__all__ = ["MT5Connector"]
