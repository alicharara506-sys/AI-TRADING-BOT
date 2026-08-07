from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from connectors.mt5.api import TIMEFRAME_MAP
from connectors.mt5.connector import MT5Connector
from core.event_bus.bus import EventBus
from core.interfaces.events import AccountStateChanged
from core.interfaces.types import Symbol, Timeframe
from core.interfaces.validation import CheckResult, ValidationReport
from live_trading.runner import LiveRunner, LiveRunnerConfig, LiveRunnerError
from strategies.pattern.fibonacci_elliott_wave import FibonacciElliottWaveStrategy
from tests.support.fake_mt5_api import FakeMT5Api

_SYMBOL_NAME = "EURUSD"
_TIMEFRAME = Timeframe.M15


class _AlwaysPassPipeline:
    """Stub pipeline used to test LiveRunner's own wiring (connect -> preflight
    -> live loop -> stop) independently of whether a real SmaCrossoverStrategy
    happens to produce a validation-passing trade history on given bars --
    that math is already covered by tests/unit/live_trading/test_preflight.py.
    """

    def run(
        self, *, strategy_name: str, trade_returns: list[float], bar_timestamps: list[datetime]
    ) -> ValidationReport:
        return ValidationReport(
            strategy_name=strategy_name,
            checks=(CheckResult(name="stub_always_passes", passed=True),),
        )


def _flat_rates(count: int) -> list[dict[str, object]]:
    start = 1_700_000_000
    return [
        {
            "time": start + i * 900,
            "open": 1.10,
            "high": 1.10,
            "low": 1.10,
            "close": 1.10,
            "tick_volume": 1,
        }
        for i in range(count)
    ]


def _make_connector(api: FakeMT5Api, event_bus: EventBus) -> MT5Connector:
    return MT5Connector(api, event_bus, login=1, password="secret", server="Demo")


@pytest.mark.asyncio
async def test_run_forever_refuses_to_trade_when_validation_fails() -> None:
    """No historical crossovers -> zero trades -> fails the Validation
    Pipeline's own minimum-trade-count check -> LiveRunnerError, and -- the
    property that actually matters -- not a single order ever reaches the
    (fake) broker.
    """
    api = FakeMT5Api()
    api.rates[(_SYMBOL_NAME, TIMEFRAME_MAP[_TIMEFRAME.value])] = _flat_rates(5)
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    config = LiveRunnerConfig(
        symbol=Symbol(name=_SYMBOL_NAME), timeframe=_TIMEFRAME, history_bar_count=5
    )
    runner = LiveRunner(connector, config, event_bus)

    with pytest.raises(LiveRunnerError):
        await runner.run_forever()

    assert api.sent_requests == []
    assert connector.is_connected()  # connect() ran; stop()/disconnect() never reached
    await connector.disconnect()


@pytest.mark.asyncio
async def test_run_forever_starts_the_live_loop_and_stops_cleanly() -> None:
    api = FakeMT5Api()
    api.rates[(_SYMBOL_NAME, TIMEFRAME_MAP[_TIMEFRAME.value])] = _flat_rates(5)
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    account_states: list[object] = []
    event_bus.subscribe(AccountStateChanged, lambda e: account_states.append(e))

    config = LiveRunnerConfig(
        symbol=Symbol(name=_SYMBOL_NAME),
        timeframe=_TIMEFRAME,
        history_bar_count=5,
        account_poll_interval_seconds=0.01,
    )
    runner = LiveRunner(connector, config, event_bus, pipeline=_AlwaysPassPipeline())  # type: ignore[arg-type]

    preflight_calls: list[bool] = []

    async def _stop_after_a_few_iterations() -> None:
        while len(account_states) < 2:
            await asyncio.sleep(0.005)
        runner.stop()

    stopper = asyncio.create_task(_stop_after_a_few_iterations())
    report = await runner.run_forever(
        on_preflight_complete=lambda r, returns: preflight_calls.append(r.passed)
    )
    await stopper

    assert report.passed
    assert preflight_calls == [True]
    assert len(account_states) >= 2
    assert connector.is_connected() is False


@pytest.mark.asyncio
async def test_preflight_uses_the_overridden_strategy_factory() -> None:
    """LiveRunner defaults to SmaCrossoverStrategy but must actually use
    whatever strategy_factory/strategy_name is passed in -- proves the
    override plumbs all the way through to run_preflight_backtest, not just
    that it type-checks.
    """
    api = FakeMT5Api()
    api.rates[(_SYMBOL_NAME, TIMEFRAME_MAP[_TIMEFRAME.value])] = _flat_rates(5)
    event_bus = EventBus()
    connector = _make_connector(api, event_bus)
    config = LiveRunnerConfig(
        symbol=Symbol(name=_SYMBOL_NAME), timeframe=_TIMEFRAME, history_bar_count=5
    )
    runner = LiveRunner(
        connector,
        config,
        event_bus,
        strategy_factory=FibonacciElliottWaveStrategy,
        strategy_name=FibonacciElliottWaveStrategy.strategy_name,
    )

    report, trade_returns = await runner.preflight()

    assert report.strategy_name == "fibonacci_elliott_wave"
    assert trade_returns == []  # flat bars -> no impulse ever detected
    await connector.disconnect()
