from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from connectors.mt5.api import (
    DEAL_ENTRY_IN,
    DEAL_ENTRY_OUT,
    ORDER_TYPE_BUY,
    ORDER_TYPE_SELL,
    TIMEFRAME_MAP,
    TRADE_ACTION_DEAL,
    TRADE_ACTION_SLTP,
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
from tests.support.fake_mt5_api import (
    FakeDeal,
    FakeMT5Api,
    FakeOrderResult,
    FakePosition,
    FakeTick,
)


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
async def test_get_historical_bars_skips_current_forming_bar() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)
    api.rates[("EURUSD", TIMEFRAME_MAP["M1"])] = [
        {
            "time": 1_700_000_000 + i * 60,
            "open": 1.10 + i * 0.001,
            "high": 1.11 + i * 0.001,
            "low": 1.09 + i * 0.001,
            "close": 1.105 + i * 0.001,
            "tick_volume": 100 + i,
        }
        for i in range(5)
    ]

    bars = await connector.get_historical_bars(Symbol(name="EURUSD"), Timeframe.M1, 3)

    assert len(bars) == 3
    assert bars[0].open == pytest.approx(1.101)
    assert bars[0].close == pytest.approx(1.106)
    assert bars[0].volume == 101
    assert bars[-1].timestamp > bars[0].timestamp


@pytest.mark.asyncio
async def test_get_historical_bars_unknown_symbol_returns_empty() -> None:
    api = FakeMT5Api()
    connector = _make_connector(api)

    bars = await connector.get_historical_bars(Symbol(name="GBPJPY"), Timeframe.M1, 10)

    assert bars == []


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
    api.next_order_result = FakeOrderResult(retcode=10004, comment="requote")
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
        FakePosition(ticket=42, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.5, price_open=1.1)
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
        FakePosition(ticket=7, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.1, price_open=1.1)
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
        FakePosition(ticket=9, symbol="EURUSD", type=ORDER_TYPE_BUY, volume=0.3, price_open=1.1)
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
        FakeDeal(
            position_id=5,
            symbol="EURUSD",
            type=ORDER_TYPE_BUY,
            volume=0.2,
            price=1.1000,
            time=1000.0,
            profit=0.0,
            entry=DEAL_ENTRY_IN,
        ),
        FakeDeal(
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

    api.ticks["EURUSD"] = FakeTick(time=1000.0, bid=1.1000, ask=1.1002, volume=5.0)
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
