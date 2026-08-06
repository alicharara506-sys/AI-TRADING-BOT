from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from connectors.mt4.connector import MT4Connector
from connectors.mt4.protocol import ACTION_SUBSCRIBE_BARS, ACTION_SUBSCRIBE_TICKS
from connectors.transport.zeromq import ZmqRequester, ZmqSubscriber
from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed, ConnectionStateChanged, TickReceived
from core.interfaces.types import (
    AccountMode,
    ConnectionState,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    Timeframe,
)
from tests.support.fake_mt4_terminal import FakeMT4Terminal

_port_counter = itertools.count(28800)


def _addresses() -> tuple[str, str]:
    command_port = next(_port_counter)
    market_port = next(_port_counter)
    return f"tcp://127.0.0.1:{command_port}", f"tcp://127.0.0.1:{market_port}"


@contextlib.asynccontextmanager
async def _harness() -> AsyncIterator[tuple[FakeMT4Terminal, MT4Connector, EventBus]]:
    command_address, market_address = _addresses()
    terminal = FakeMT4Terminal(command_address, market_address)
    terminal.start()
    event_bus = EventBus()
    requester = ZmqRequester(command_address, timeout_seconds=5.0)
    subscriber = ZmqSubscriber(market_address, topics=["tick", "bar"])
    connector = MT4Connector(requester, subscriber, event_bus)
    try:
        yield terminal, connector, event_bus
    finally:
        requester.close()
        subscriber.close()
        await terminal.stop()


def _order(correlation_id: str = "corr-1") -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_connect_success_publishes_connected() -> None:
    async with _harness() as (_terminal, connector, event_bus):
        states: list[ConnectionState] = []
        event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))

        await connector.connect()

        assert connector.is_connected()
        assert states == [ConnectionState.CONNECTED]


@pytest.mark.asyncio
async def test_connect_failure_raises() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.connect_result = {"ok": False, "error": "no terminal running"}

        with pytest.raises(ConnectionError):
            await connector.connect()

        assert not connector.is_connected()


@pytest.mark.asyncio
async def test_disconnect_publishes_disconnected() -> None:
    async with _harness() as (_terminal, connector, event_bus):
        await connector.connect()
        states: list[ConnectionState] = []
        event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))

        await connector.disconnect()

        assert not connector.is_connected()
        assert states == [ConnectionState.DISCONNECTED]


@pytest.mark.asyncio
async def test_get_symbol_info_maps_fields() -> None:
    async with _harness() as (_terminal, connector, _event_bus):
        info = await connector.get_symbol_info(Symbol(name="EURUSD"))

        assert info.digits == 5
        assert info.contract_size == pytest.approx(100_000.0)
        assert info.account_mode == AccountMode.HEDGING


@pytest.mark.asyncio
async def test_get_symbol_info_unknown_symbol_raises() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.symbol_info_ok = False

        with pytest.raises(LookupError):
            await connector.get_symbol_info(Symbol(name="GBPJPY"))


@pytest.mark.asyncio
async def test_get_account_state_maps_fields() -> None:
    async with _harness() as (_terminal, connector, _event_bus):
        state = await connector.get_account_state()

        assert state.balance == pytest.approx(10_000.0)
        assert state.currency == "USD"
        assert state.margin_level is None


@pytest.mark.asyncio
async def test_submit_market_order_success() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.next_order_result = {"ok": True, "ticket": 42, "price": 1.10055}

        ack = await connector.submit_order(_order())

        assert ack.status == OrderStatus.FILLED
        assert ack.broker_order_id == "42"
        assert ack.fill_price == pytest.approx(1.10055)
        sent = terminal.received_requests[-1]
        assert sent["symbol"] == "EURUSD"
        assert sent["side"] == "buy"


@pytest.mark.asyncio
async def test_submit_order_rejected() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.next_order_result = {"ok": False, "error": "no quotes"}

        ack = await connector.submit_order(_order())

        assert ack.status == OrderStatus.REJECTED
        assert ack.reason == "no quotes"


@pytest.mark.asyncio
async def test_submit_non_market_order_raises() -> None:
    async with _harness() as (_terminal, connector, _event_bus):
        request = OrderRequest(
            correlation_id="corr-2",
            symbol=Symbol(name="EURUSD"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            volume=0.1,
            price=1.05,
        )

        with pytest.raises(NotImplementedError):
            await connector.submit_order(request)


@pytest.mark.asyncio
async def test_modify_position_success_and_failure() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        await connector.modify_position("7", stop_loss=1.09, take_profit=1.12)
        sent = terminal.received_requests[-1]
        assert sent["ticket"] == "7"
        assert sent["stop_loss"] == pytest.approx(1.09)

        terminal.next_modify_result = {"ok": False, "error": "invalid stops"}
        with pytest.raises(RuntimeError):
            await connector.modify_position("7", stop_loss=1.09)


@pytest.mark.asyncio
async def test_close_position_success_and_failure() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        await connector.close_position("9", volume=0.2)
        sent = terminal.received_requests[-1]
        assert sent["ticket"] == "9"
        assert sent["volume"] == pytest.approx(0.2)

        terminal.next_close_result = {"ok": False, "error": "market closed"}
        with pytest.raises(RuntimeError):
            await connector.close_position("9")


@pytest.mark.asyncio
async def test_get_open_positions_maps_fields() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.open_positions = [
            {
                "ticket": 5,
                "symbol": "EURUSD",
                "side": "buy",
                "volume": 0.3,
                "open_price": 1.1,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            }
        ]

        positions = await connector.get_open_positions()

        assert len(positions) == 1
        assert positions[0].position_id == "5"
        assert positions[0].side == OrderSide.BUY
        assert positions[0].stop_loss is None


@pytest.mark.asyncio
async def test_get_trade_history_maps_fields() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        terminal.trade_history = [
            {
                "trade_id": 1,
                "symbol": "EURUSD",
                "side": "buy",
                "volume": 0.1,
                "open_price": 1.10,
                "close_price": 1.11,
                "open_time": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                "close_time": datetime(2026, 1, 2, tzinfo=UTC).isoformat(),
                "profit": 10.0,
            }
        ]

        trades = await connector.get_trade_history(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)
        )

        assert len(trades) == 1
        assert trades[0].profit == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_subscribe_ticks_and_bars_send_requests() -> None:
    async with _harness() as (terminal, connector, _event_bus):
        await connector.subscribe_ticks(Symbol(name="EURUSD"))
        await connector.subscribe_bars(Symbol(name="EURUSD"), Timeframe.M1)

        actions = [request["action"] for request in terminal.received_requests]
        assert actions == [ACTION_SUBSCRIBE_TICKS, ACTION_SUBSCRIBE_BARS]


@pytest.mark.asyncio
async def test_listen_republishes_ticks_and_bars_onto_the_event_bus() -> None:
    async with _harness() as (terminal, connector, event_bus):
        ticks: list[TickReceived] = []
        bars: list[BarClosed] = []
        event_bus.subscribe(TickReceived, lambda e: ticks.append(e))
        event_bus.subscribe(BarClosed, lambda e: bars.append(e))

        listen_task = asyncio.create_task(connector.listen())
        try:
            await asyncio.sleep(0.2)  # let the SUB socket finish connecting

            await terminal.publish_tick(
                {
                    "symbol": "EURUSD",
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "bid": 1.0998,
                    "ask": 1.1000,
                }
            )
            await terminal.publish_bar(
                {
                    "symbol": "EURUSD",
                    "timeframe": "M1",
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                    "open": 1.10,
                    "high": 1.11,
                    "low": 1.09,
                    "close": 1.105,
                }
            )

            for _ in range(20):
                if ticks and bars:
                    break
                await asyncio.sleep(0.05)

            assert len(ticks) == 1
            assert ticks[0].tick.bid == pytest.approx(1.0998)
            assert len(bars) == 1
            assert bars[0].bar.close == pytest.approx(1.105)
        finally:
            listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await listen_task
