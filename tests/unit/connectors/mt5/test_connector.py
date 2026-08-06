from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any

import pytest

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
)
from connectors.mt5.connector import MT5Connector
from connectors.mt_common.reconnect import ReconnectPolicy
from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed, ConnectionStateChanged, TickReceived
from core.interfaces.types import (
    ConnectionState,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    Timeframe,
)


@dataclass
class _FakeAccount:
    balance: float = 10_000.0
    equity: float = 10_000.0
    margin: float = 0.0
    margin_free: float = 10_000.0
    margin_level: float = 0.0
    currency: str = "USD"
    margin_mode: int = ACCOUNT_MARGIN_MODE_RETAIL_HEDGING


@dataclass
class _FakeSymbolInfo:
    digits: int = 5
    point: float = 0.00001
    trade_contract_size: float = 100_000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01


@dataclass
class _FakeTick:
    time: float
    bid: float
    ask: float
    volume: float = 0.0


@dataclass
class _FakePosition:
    ticket: int
    symbol: str
    type: int
    volume: float
    price_open: float
    sl: float = 0.0
    tp: float = 0.0


@dataclass
class _FakeOrderResult:
    retcode: int
    order: int = 0
    comment: str = ""
    price: float = 0.0


@dataclass
class _FakeDeal:
    position_id: int
    symbol: str
    type: int
    volume: float
    price: float
    time: float
    profit: float
    entry: int


class FakeMT5Api:
    """Structurally satisfies MT5Api without needing the real MetaTrader5 package."""

    def __init__(self) -> None:
        self.account = _FakeAccount()
        self.symbols: dict[str, _FakeSymbolInfo] = {"EURUSD": _FakeSymbolInfo()}
        self.ticks: dict[str, _FakeTick] = {}
        self.rates: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self.positions: list[_FakePosition] = []
        self.deals: list[_FakeDeal] = []
        self.sent_requests: list[dict[str, Any]] = []
        self.next_order_result = _FakeOrderResult(retcode=TRADE_RETCODE_DONE, order=1, price=1.1005)
        self.initialize_result = True
        self.login_result = True

    def initialize(self, **kwargs: Any) -> bool:
        return self.initialize_result

    def login(self, login: int, password: str, server: str) -> bool:
        return self.login_result

    def shutdown(self) -> None:
        return None

    def last_error(self) -> tuple[int, str]:
        return (1, "simulated failure")

    def account_info(self) -> Any:
        return self.account

    def symbol_info(self, symbol: str) -> Any:
        return self.symbols.get(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self.ticks.get(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return self.rates.get((symbol, timeframe), [])[start_pos : start_pos + count]

    def order_send(self, request: dict[str, Any]) -> Any:
        self.sent_requests.append(request)
        return self.next_order_result

    def positions_get(self, *, symbol: str | None = None) -> Any:
        if symbol is None:
            return list(self.positions)
        return [p for p in self.positions if p.symbol == symbol]

    def history_deals_get(self, date_from: Any, date_to: Any) -> Any:
        return list(self.deals)


def _make_connector(
    api: FakeMT5Api, event_bus: EventBus | None = None, **kwargs: Any
) -> MT5Connector:
    return MT5Connector(
        api, event_bus or EventBus(), login=1, password="secret", server="Demo", **kwargs
    )


@pytest.mark.asyncio
async def test_connect_success_publishes_connected() -> None:
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    states: list[ConnectionState] = []
    event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))

    await connector.connect()

    assert connector.is_connected()
    assert states == [ConnectionState.CONNECTED]


@pytest.mark.asyncio
async def test_connect_failure_raises() -> None:
    api = FakeMT5Api()
    api.initialize_result = False
    connector = _make_connector(api)

    with pytest.raises(ConnectionError):
        await connector.connect()

    assert not connector.is_connected()


@pytest.mark.asyncio
async def test_disconnect_publishes_disconnected() -> None:
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    await connector.connect()

    states: list[ConnectionState] = []
    event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))
    await connector.disconnect()

    assert not connector.is_connected()
    assert states == [ConnectionState.DISCONNECTED]


@pytest.mark.asyncio
async def test_get_account_state_maps_fields() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)

    state = await connector.get_account_state()

    assert state.balance == 10_000.0
    assert state.equity == 10_000.0
    assert state.free_margin == 10_000.0
    assert state.currency == "USD"
    assert state.margin_level is None  # 0.0 from MT5 means "not applicable"


@pytest.mark.asyncio
async def test_get_symbol_info_maps_fields_and_hedging_mode() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)

    info = await connector.get_symbol_info(Symbol(name="EURUSD"))

    assert info.digits == 5
    assert info.contract_size == 100_000.0
    from core.interfaces.types import AccountMode

    assert info.account_mode == AccountMode.HEDGING


@pytest.mark.asyncio
async def test_get_symbol_info_unknown_symbol_raises() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)

    with pytest.raises(LookupError):
        await connector.get_symbol_info(Symbol(name="GBPJPY"))


@pytest.mark.asyncio
async def test_submit_market_order_success() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)
    request = OrderRequest(
        correlation_id="corr-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
        stop_loss=1.0950,
        take_profit=1.1100,
    )

    ack = await connector.submit_order(request)

    assert ack.status == OrderStatus.FILLED
    assert ack.broker_order_id == "1"
    assert ack.fill_price == pytest.approx(1.1005)
    sent = api.sent_requests[-1]
    assert sent["action"] == TRADE_ACTION_DEAL
    assert sent["type"] == ORDER_TYPE_BUY
    assert sent["sl"] == pytest.approx(1.0950)
    assert sent["tp"] == pytest.approx(1.1100)


@pytest.mark.asyncio
async def test_submit_order_rejected_when_retcode_not_done() -> None:
    api = FakeMT5Api()
    api.next_order_result = _FakeOrderResult(retcode=10004, comment="requote")
    connector = _make_connector(api)
    request = OrderRequest(
        correlation_id="corr-2",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=0.1,
    )

    ack = await connector.submit_order(request)

    assert ack.status == OrderStatus.REJECTED
    assert "requote" in (ack.reason or "")


@pytest.mark.asyncio
async def test_submit_non_market_order_raises() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)
    request = OrderRequest(
        correlation_id="corr-3",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        volume=0.1,
        price=1.0900,
    )

    with pytest.raises(NotImplementedError):
        await connector.submit_order(request)


@pytest.mark.asyncio
async def test_get_open_positions_maps_fields_and_zero_sl_tp_to_none() -> None:
    api = FakeMT5Api()
    api.positions.append(
        _FakePosition(ticket=42, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.5, price_open=1.1)
    )
    connector = _make_connector(api)

    positions = await connector.get_open_positions()

    assert len(positions) == 1
    position = positions[0]
    assert position.position_id == "42"
    assert position.side == OrderSide.BUY
    assert position.stop_loss is None
    assert position.take_profit is None


@pytest.mark.asyncio
async def test_modify_position_sends_sltp_request() -> None:
    api = FakeMT5Api()
    api.positions.append(
        _FakePosition(ticket=7, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.1, price_open=1.1)
    )
    connector = _make_connector(api)

    await connector.modify_position("7", stop_loss=1.09, take_profit=1.12)

    sent = api.sent_requests[-1]
    assert sent["action"] == TRADE_ACTION_SLTP
    assert sent["position"] == 7
    assert sent["sl"] == pytest.approx(1.09)
    assert sent["tp"] == pytest.approx(1.12)


@pytest.mark.asyncio
async def test_modify_unknown_position_raises() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)

    with pytest.raises(LookupError):
        await connector.modify_position("999", stop_loss=1.0)


@pytest.mark.asyncio
async def test_close_position_sends_opposite_side_deal() -> None:
    api = FakeMT5Api()
    api.positions.append(
        _FakePosition(ticket=9, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.3, price_open=1.1)
    )
    connector = _make_connector(api)

    await connector.close_position("9")

    sent = api.sent_requests[-1]
    assert sent["action"] == TRADE_ACTION_DEAL
    assert sent["type"] == ORDER_TYPE_SELL
    assert sent["volume"] == pytest.approx(0.3)
    assert sent["position"] == 9


@pytest.mark.asyncio
async def test_get_trade_history_pairs_entry_and_exit_deals() -> None:
    api = FakeMT5Api()
    api.deals = [
        _FakeDeal(
            position_id=5,
            symbol="EURUSD",
            type=ORDER_TYPE_BUY,
            volume=0.2,
            price=1.1000,
            time=1000.0,
            profit=0.0,
            entry=DEAL_ENTRY_IN,
        ),
        _FakeDeal(
            position_id=5,
            symbol="EURUSD",
            type=ORDER_TYPE_SELL,
            volume=0.2,
            price=1.1050,
            time=2000.0,
            profit=100.0,
            entry=DEAL_ENTRY_OUT,
        ),
    ]
    connector = _make_connector(api)

    from datetime import UTC, datetime

    trades = await connector.get_trade_history(
        datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.trade_id == "5"
    assert trade.side == OrderSide.BUY
    assert trade.open_price == pytest.approx(1.1000)
    assert trade.close_price == pytest.approx(1.1050)
    assert trade.profit == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_poll_once_publishes_new_events_and_dedupes_unchanged() -> None:
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    symbol = Symbol(name="EURUSD")
    await connector.subscribe_ticks(symbol)
    await connector.subscribe_bars(symbol, Timeframe.M1)

    api.ticks["EURUSD"] = _FakeTick(time=1000.0, bid=1.1000, ask=1.1002, volume=5.0)
    api.rates[("EURUSD", TIMEFRAME_MAP["M1"])] = [
        {"time": 2000.0, "open": 1.1, "high": 1.2, "low": 1.05, "close": 1.15, "tick_volume": 42.0}
    ]

    ticks_received: list[TickReceived] = []
    bars_received: list[BarClosed] = []
    event_bus.subscribe(TickReceived, lambda e: ticks_received.append(e))
    event_bus.subscribe(BarClosed, lambda e: bars_received.append(e))

    await connector.poll_once()

    assert len(ticks_received) == 1
    assert ticks_received[0].tick.bid == pytest.approx(1.1000)
    assert len(bars_received) == 1
    assert bars_received[0].bar.close == pytest.approx(1.15)

    await connector.poll_once()

    assert len(ticks_received) == 1
    assert len(bars_received) == 1


@pytest.mark.asyncio
async def test_poll_loop_reconnects_after_failure() -> None:
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = _make_connector(
        api,
        event_bus,
        reconnect_policy=ReconnectPolicy(initial_delay=0.01, max_delay=0.01, multiplier=2.0),
        poll_interval=0.01,
    )
    await connector.subscribe_ticks(Symbol(name="EURUSD"))
    await connector.connect()

    states: list[ConnectionState] = []
    event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))

    call_count = 0

    def failing_then_ok(symbol: str) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated connection drop")
        return None

    api.symbol_info_tick = failing_then_ok  # type: ignore[method-assign]

    task = asyncio.create_task(connector._poll_loop())
    await asyncio.sleep(0.3)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert ConnectionState.LOST in states
    assert states.count(ConnectionState.CONNECTED) >= 1
