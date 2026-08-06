from __future__ import annotations

import asyncio
import contextlib
import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from connectors.mt4.connector import MT4Connector
from connectors.mt5.connector import MT5Connector
from connectors.transport.zeromq import ZmqRequester, ZmqSubscriber
from core.event_bus.bus import EventBus
from core.interfaces.events import ConnectionStateChanged
from core.interfaces.types import (
    ConnectionState,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
)
from core.kernel.clock import TestClock
from tests.support.fake_mt4_terminal import FakeMT4Terminal
from tests.support.fake_mt5_api import FakeMT5Api

_port_counter = itertools.count(28900)


def _mt4_addresses() -> tuple[str, str]:
    command_port = next(_port_counter)
    market_port = next(_port_counter)
    return f"tcp://127.0.0.1:{command_port}", f"tcp://127.0.0.1:{market_port}"


def _order() -> OrderRequest:
    return OrderRequest(
        correlation_id="chaos-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


async def test_mt5_order_failure_flips_connection_state_and_recovers() -> None:
    """Before this phase, a mid-order MT5Api failure propagated the exception
    but left `_connected` stale (True) with no ConnectionStateChanged event --
    the rest of the system had no way to learn the terminal was down. This
    proves the fix end to end: the failure is observed, state flips to LOST,
    and a real subsequent order succeeds once the API recovers -- not just
    that an internal counter changed.
    """
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = MT5Connector(api, event_bus, login=1, password="secret", server="Demo")
    await connector.connect()
    assert connector.is_connected()

    states: list[ConnectionState] = []
    event_bus.subscribe(ConnectionStateChanged, lambda e: states.append(e.state))

    def _raise(request: dict[str, Any]) -> Any:
        raise RuntimeError("simulated broker outage")

    api.order_send = _raise  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="simulated broker outage"):
        await connector.submit_order(_order())

    assert not connector.is_connected()
    assert states == [ConnectionState.LOST]

    del api.order_send  # restore the real (working) bound method
    await connector.connect()
    assert connector.is_connected()
    assert states[-1] == ConnectionState.CONNECTED

    ack = await connector.submit_order(_order())
    assert ack.status == OrderStatus.FILLED


async def test_mt5_query_failure_also_flips_connection_state() -> None:
    """The fix isn't order-path-specific -- any direct MT5Api call failing
    (here, an account query) must surface the same way."""
    api = FakeMT5Api()
    event_bus = EventBus()
    connector = MT5Connector(api, event_bus, login=1, password="secret", server="Demo")
    await connector.connect()

    def _raise() -> Any:
        raise RuntimeError("simulated broker outage")

    api.account_info = _raise  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await connector.get_account_state()

    assert not connector.is_connected()


async def test_mt4_request_timeout_recovers_for_the_next_call() -> None:
    """ZeroMQ REQ sockets enforce strict send/recv alternation: a naive
    implementation that times out on recv() without recreating the socket
    leaves it permanently unable to send again. This proves the fix: after a
    stalled EA causes one command to time out, the very next command on the
    same MT4Connector still succeeds.
    """
    command_address, market_address = _mt4_addresses()
    terminal = FakeMT4Terminal(command_address, market_address)
    terminal.start()
    event_bus = EventBus()
    requester = ZmqRequester(command_address, timeout_seconds=0.1)
    subscriber = ZmqSubscriber(market_address, topics=["tick", "bar"])
    connector = MT4Connector(requester, subscriber, event_bus)
    try:
        terminal.stall_next_n_requests = 1
        terminal.stall_seconds = 0.3

        with pytest.raises(TimeoutError):
            await connector.connect()
        assert not connector.is_connected()

        # Let the stalled reply land and the fake terminal loop back to
        # receive() before sending the next command.
        await asyncio.sleep(0.35)

        await connector.connect()
        assert connector.is_connected()
    finally:
        requester.close()
        subscriber.close()
        await terminal.stop()


async def test_mt4_heartbeat_state_reflects_market_data_silence() -> None:
    """HeartbeatMonitor existed since Phase 3 but was never wired into either
    connector. This wires it into MT4Connector.listen() and proves it against
    a real tick delivered over genuine ZeroMQ PUB/SUB sockets, with a
    TestClock driving deterministic CONNECTED -> DEGRADED -> LOST transitions.
    """
    command_address, market_address = _mt4_addresses()
    terminal = FakeMT4Terminal(command_address, market_address)
    terminal.start()
    event_bus = EventBus()
    requester = ZmqRequester(command_address, timeout_seconds=1.0)
    subscriber = ZmqSubscriber(market_address, topics=["tick", "bar"])
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    connector = MT4Connector(
        requester,
        subscriber,
        event_bus,
        clock=clock,
        heartbeat_degraded_after=timedelta(seconds=10),
        heartbeat_lost_after=timedelta(seconds=30),
    )

    listen_task = asyncio.create_task(connector.listen())
    try:
        assert connector.heartbeat_state() == ConnectionState.DISCONNECTED

        await asyncio.sleep(0.2)  # let the SUB socket finish connecting
        await terminal.publish_tick(
            {
                "symbol": "EURUSD",
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                "bid": 1.0998,
                "ask": 1.1000,
            }
        )
        for _ in range(20):
            if connector.heartbeat_state() == ConnectionState.CONNECTED:
                break
            await asyncio.sleep(0.05)
        assert connector.heartbeat_state() == ConnectionState.CONNECTED

        clock.advance(timedelta(seconds=15))
        assert connector.heartbeat_state() == ConnectionState.DEGRADED

        clock.advance(timedelta(seconds=20))
        assert connector.heartbeat_state() == ConnectionState.LOST
    finally:
        listen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listen_task
        requester.close()
        subscriber.close()
        await terminal.stop()
