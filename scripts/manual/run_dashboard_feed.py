"""Dashboard data feed: connects to a REAL MT5 account, watches a chosen
Strategy for signals, and persists everything the Streamlit dashboard
(scripts/manual/dashboard/app.py) reads -- account snapshots, signals with
their full agent-voting evidence, and stop-loss/take-profit suggestions --
into a local SQLite database. This script never submits an order: it is
the observability half of live_trading, not the execution half. Run
run_live_strategy.py or watch_signals.py separately if you want this
platform to actually act on a signal.

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

Pick a strategy the same way run_live_strategy.py / watch_signals.py do:
    $env:MT5_STRATEGY = "sma_crossover"          # default
    $env:MT5_STRATEGY = "fibonacci_elliott_wave"

Optional overrides (all have sensible defaults):
    $env:MT5_TRADE_TIMEFRAME = "M15"
    $env:MT5_HISTORY_BAR_COUNT = "2000"
    $env:MT5_ATR_PERIOD = "14"
    $env:MT5_ATR_MULTIPLE = "2.0"
    $env:MT5_RISK_REWARD_RATIO = "1.5"
    $env:MT5_FAST_PERIOD = "5"                    # sma_crossover only
    $env:MT5_SLOW_PERIOD = "20"                   # sma_crossover only
    $env:MT5_SWING_ARM = "2"                      # fibonacci_elliott_wave only
    $env:MT5_ELLIOTT_LOOKBACK = "300"             # fibonacci_elliott_wave only
    $env:MT5_DASHBOARD_DB_PATH = "dashboard.db"   # SQLite file the dashboard reads
    $env:MT5_ACCOUNT_SNAPSHOT_INTERVAL_SECONDS = "30"

Run (from the repository root, with the venv active):
    python scripts\\manual\\run_dashboard_feed.py

Then, in a second PowerShell window (same venv), run the dashboard itself:
    pip install -e ".[dashboard]"
    streamlit run scripts\\manual\\dashboard\\app.py -- --db-path dashboard.db

Stop this feed any time with Ctrl+C.
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

    from connectors.mt5.connector import MT5Connector
    from connectors.mt_common.symbols import SymbolMapper
    from core.event_bus.bus import EventBus
    from core.interfaces.events import BarClosed
    from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe, TradeSignal
    from core.risk.sizing import FixedVolumeSizingModel
    from database.repository import SqliteSignalRepository
    from decision_engine.engine import DecisionEngine
    from live_trading.signal_watcher import SignalWatcher
    from live_trading.strategy_selection import SMA_CROSSOVER, build_strategy_factory

    login = int(_require_env("MT5_LOGIN"))
    password = _require_env("MT5_PASSWORD")
    server = _require_env("MT5_SERVER")
    symbol_name = _require_env("MT5_TRADE_SYMBOL")
    symbol_suffix = os.environ.get("MT5_SYMBOL_SUFFIX", "")
    timeframe_name = os.environ.get("MT5_TRADE_TIMEFRAME", "M15")
    strategy_choice = os.environ.get("MT5_STRATEGY", SMA_CROSSOVER)
    history_bar_count = int(os.environ.get("MT5_HISTORY_BAR_COUNT", "2000"))
    atr_period = int(os.environ.get("MT5_ATR_PERIOD", "14"))
    atr_multiple = float(os.environ.get("MT5_ATR_MULTIPLE", "2.0"))
    risk_reward_ratio = float(os.environ.get("MT5_RISK_REWARD_RATIO", "1.5"))
    db_path = os.environ.get("MT5_DASHBOARD_DB_PATH", "dashboard.db")
    snapshot_interval = float(os.environ.get("MT5_ACCOUNT_SNAPSHOT_INTERVAL_SECONDS", "30"))

    try:
        timeframe = Timeframe(timeframe_name)
    except ValueError:
        valid = ", ".join(t.value for t in Timeframe)
        print(
            f"Invalid MT5_TRADE_TIMEFRAME '{timeframe_name}'. Valid values: {valid}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        strategy_factory, strategy_name = build_strategy_factory(
            strategy_choice,
            fast_period=int(os.environ.get("MT5_FAST_PERIOD", "5")),
            slow_period=int(os.environ.get("MT5_SLOW_PERIOD", "20")),
            swing_arm=int(os.environ.get("MT5_SWING_ARM", "2")),
            lookback=int(os.environ.get("MT5_ELLIOTT_LOOKBACK", "300")),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
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
    repository = SqliteSignalRepository(f"sqlite:///{db_path}")

    print(f"Connecting to server='{server}' login={login} ...")
    try:
        await connector.connect()
    except ConnectionError as exc:
        print(f"FAILED to connect: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Connected: {connector.is_connected()}")
    print(f"Strategy: {strategy_name}")
    print(f"Writing to: {db_path}")

    print(
        f"\nFetching {history_bar_count} historical {timeframe.value} bars "
        f"for {symbol.canonical}..."
    )
    try:
        bars = await connector.get_historical_bars(symbol, timeframe, history_bar_count)
    except LookupError as exc:
        print(f"Could not fetch historical bars: {exc}", file=sys.stderr)
        sys.exit(1)
    repository.bulk_record_bars(bars)
    event_bus.subscribe(BarClosed, lambda e: repository.record_bar(e.bar))

    decision_engine = DecisionEngine(
        FixedVolumeSizingModel(0.01),
        atr_period=atr_period,
        atr_multiple=atr_multiple,
        risk_reward_ratio=risk_reward_ratio,
    )

    def _on_signal(signal: TradeSignal, bar: Bar, history: tuple[Bar, ...]) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        context = MarketContext(symbol=symbol, bars=history)
        report = decision_engine.decide(signal, context, equity=1.0)
        repository.record_signal(report, strategy_name=strategy_name, entry_price=bar.close)
        print(
            f"\n*** SIGNAL: {signal.direction.value.upper()} {signal.symbol.canonical} "
            f"-- bar close {bar.close} at {bar.timestamp.isoformat()} (detected {now}) "
            f"-- recorded to {db_path} ***"
        )

    strategy = strategy_factory()
    SignalWatcher(symbol, strategy, event_bus, on_signal=_on_signal, history=bars)

    await connector.start()
    await connector.subscribe_bars(symbol, timeframe)
    print(
        f"\nWatching {symbol.canonical} {timeframe.value}. Recording signals and account "
        f"snapshots every {snapshot_interval:.0f}s. Press Ctrl+C to stop.\n"
    )

    try:
        while True:
            account = await connector.get_account_state()
            repository.record_account_snapshot(account)
            await asyncio.sleep(snapshot_interval)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await connector.stop()
        print("Disconnected.")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
