"""Signal-only watcher: prints BUY/SELL alerts for SmaCrossoverStrategy
against a REAL MT5 account without ever submitting an order.

Use this instead of scripts/manual/run_live_strategy.py when your broker's
server blocks automated order submission (MT5 retcode 10026, "AutoTrading
disabled by server") -- a server-side permission this platform cannot grant
or route around. You still get a real connection, real market data, and a
real strategy watching it; you just place the trade yourself in the MT5
terminal when a signal prints.

This must run on the same Windows machine as your MT5 terminal, same as
scripts/manual/mt5_connectivity_check.py.

Setup (PowerShell, run once per session -- same as the other manual scripts):
    py -m venv .venv
    .venv\\Scripts\\Activate.ps1
    pip install -e .
    pip install MetaTrader5

    $env:MT5_LOGIN = "<your account number>"
    $env:MT5_PASSWORD = "<your account password>"
    $env:MT5_SERVER = "<your broker's server name>"
    $env:MT5_TRADE_SYMBOL = "<the exact symbol name your broker uses, e.g. EURUSD>"
    $env:MT5_SYMBOL_SUFFIX = "<broker suffix if any, e.g. .gc -- see run_live_strategy.py>"

Optional overrides (all have sensible defaults):
    $env:MT5_TRADE_TIMEFRAME = "M15"      # M1/M5/M15/M30/H1/H4/D1/W1/MN1
    $env:MT5_FAST_PERIOD = "5"
    $env:MT5_SLOW_PERIOD = "20"
    $env:MT5_HISTORY_BAR_COUNT = "2000"   # used only for the informational track record below

Run (from the repository root, with the venv active):
    python scripts\\manual\\watch_signals.py

Stop any time with Ctrl+C.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import UTC, datetime


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


async def main() -> None:
    try:
        import MetaTrader5 as mt5  # type: ignore[import-not-found]
    except ImportError:
        print(
            "The real MetaTrader5 package isn't installed. Run:\n"
            "    pip install MetaTrader5\n"
            "(Windows only -- this package cannot install on Linux/macOS.)",
            file=sys.stderr,
        )
        sys.exit(1)

    from backtesting.validation.look_ahead import LookAheadBiasCheck
    from backtesting.validation.monte_carlo import MonteCarloCheck
    from backtesting.validation.pipeline import ValidationPipeline
    from backtesting.validation.walk_forward import WalkForwardCheck
    from connectors.mt5.connector import MT5Connector
    from connectors.mt_common.symbols import SymbolMapper
    from core.event_bus.bus import EventBus
    from core.interfaces.types import Bar, Symbol, Timeframe, TradeSignal
    from core.risk.sizing import FixedVolumeSizingModel
    from live_trading.preflight import run_preflight_backtest
    from live_trading.signal_watcher import SignalWatcher
    from strategies.simple.sma_crossover import SmaCrossoverStrategy

    login = int(_require_env("MT5_LOGIN"))
    password = _require_env("MT5_PASSWORD")
    server = _require_env("MT5_SERVER")
    symbol_name = _require_env("MT5_TRADE_SYMBOL")
    symbol_suffix = os.environ.get("MT5_SYMBOL_SUFFIX", "")
    timeframe_name = os.environ.get("MT5_TRADE_TIMEFRAME", "M15")
    fast_period = int(os.environ.get("MT5_FAST_PERIOD", "5"))
    slow_period = int(os.environ.get("MT5_SLOW_PERIOD", "20"))
    history_bar_count = int(os.environ.get("MT5_HISTORY_BAR_COUNT", "2000"))

    try:
        timeframe = Timeframe(timeframe_name)
    except ValueError:
        valid = ", ".join(t.value for t in Timeframe)
        print(
            f"Invalid MT5_TRADE_TIMEFRAME '{timeframe_name}'. Valid values: {valid}",
            file=sys.stderr,
        )
        sys.exit(1)

    symbol = Symbol(name=symbol_name)
    event_bus = EventBus()
    connector = MT5Connector(
        mt5,
        event_bus,
        login=login,
        password=password,
        server=server,
        symbol_mapper=SymbolMapper(suffix=symbol_suffix),
    )

    print(f"Connecting to server='{server}' login={login} ...")
    try:
        await connector.connect()
    except ConnectionError as exc:
        print(f"FAILED to connect: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Connected: {connector.is_connected()}")

    print(
        f"\nFetching {history_bar_count} historical {timeframe.value} bars for "
        f"{symbol.canonical} for context (informational only -- does not block signals)..."
    )
    try:
        bars = await connector.get_historical_bars(symbol, timeframe, history_bar_count)
        if len(bars) >= 2:
            account = await connector.get_account_state()
            pipeline = ValidationPipeline(
                walk_forward=WalkForwardCheck(max_degradation=0.5),
                monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
                look_ahead=LookAheadBiasCheck(),
            )
            report, trade_returns = await run_preflight_backtest(
                lambda: SmaCrossoverStrategy(fast_period=fast_period, slow_period=slow_period),
                bars,
                strategy_name=SmaCrossoverStrategy.strategy_name,
                starting_equity=account.equity,
                sizing_model=FixedVolumeSizingModel(1.0),
                pipeline=pipeline,
            )
            if trade_returns:
                wins = sum(1 for r in trade_returns if r > 0)
                print(
                    f"Historical track record: {len(trade_returns)} trades, "
                    f"{wins} winners ({100 * wins / len(trade_returns):.0f}%), "
                    f"net {sum(trade_returns):+.5f}"
                )
            else:
                print("Historical track record: 0 trades in the fetched bars")
            status = "PASSED" if report.passed else f"FAILED ({report.failure_summary()})"
            print(f"Validation: {status} -- shown for context only, does not block signals.")
        else:
            print("Not enough historical bars to compute a track record; continuing anyway.")
    except LookupError as exc:
        print(f"Could not fetch historical context: {exc}. Continuing anyway.")

    def _on_signal(signal: TradeSignal, bar: Bar) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        print(
            f"\n*** SIGNAL: {signal.direction.value.upper()} {signal.symbol.canonical} "
            f"-- bar close {bar.close} at {bar.timestamp.isoformat()} (detected {now}) ***\n"
            "This bot did not place a trade -- place it yourself in MT5 if you want to act on it.\n"
        )

    strategy = SmaCrossoverStrategy(fast_period=fast_period, slow_period=slow_period)
    SignalWatcher(symbol, strategy, event_bus, on_signal=_on_signal)

    await connector.start()
    await connector.subscribe_bars(symbol, timeframe)
    print(f"\nWatching {symbol.canonical} {timeframe.value} for signals. Press Ctrl+C to stop.\n")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await connector.stop()
        print("Disconnected.")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
