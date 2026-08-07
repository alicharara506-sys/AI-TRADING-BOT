"""Live (demo or real) trading runner: SmaCrossoverStrategy wired to a REAL
MT5 terminal, gated by a pre-flight backtest + Validation Pipeline run
against this account's own real history.

This must run on the same Windows machine as your MT5 terminal, same as
scripts/manual/mt5_connectivity_check.py -- read that script's docstring
first if you haven't already run it successfully.

Safety: before a single live order can be placed, this script fetches your
account's real historical bars for the symbol/timeframe you configure,
replays SmaCrossoverStrategy against them through the same backtest engine
and Validation Pipeline the rest of this platform uses
(docs/runbook/backtest-to-live.md), and refuses to proceed if that strategy
doesn't pass. There is no flag to skip this -- it is the only code path
that constructs the live execution engine (live_trading/runner.py).

Every order that is placed still passes through the Risk Engine's kill
switch, position-count limit, and daily-loss limit before it reaches the
venue, and FlipSafeExecutionEngine closes any stale opposite-side position
first (hedging accounts, like the SupremeFX-Server account this platform
was verified against, open a second position instead of netting otherwise).

This is still real trading against a real account -- run it on the demo
account first, and understand what SmaCrossoverStrategy actually does
(strategies/simple/sma_crossover.py: a fast/slow moving-average crossover)
before pointing it at money you're not prepared to lose.

Setup (PowerShell, run once per session -- same as the connectivity check):
    py -m venv .venv
    .venv\\Scripts\\Activate.ps1
    pip install -e .
    pip install MetaTrader5

    $env:MT5_LOGIN = "<your account number>"
    $env:MT5_PASSWORD = "<your account password>"
    $env:MT5_SERVER = "<your broker's server name>"
    $env:MT5_TRADE_SYMBOL = "<the exact symbol name your broker uses, e.g. EURUSD>"

Find MT5_TRADE_SYMBOL in your MT5 terminal's "Market Watch" panel (Ctrl+M).
If your broker suffixes its symbol names (e.g. Market Watch shows
"EURUSD.gc" rather than plain "EURUSD"), set the base name and the suffix
separately -- symbol names are matched case-sensitively against the
broker's own list, and this platform always uppercases the base name, so a
lowercase suffix typed directly into MT5_TRADE_SYMBOL would silently fail
to match:
    $env:MT5_TRADE_SYMBOL = "EURUSD"
    $env:MT5_SYMBOL_SUFFIX = ".gc"

Optional overrides (all have sensible defaults):
    $env:MT5_TRADE_TIMEFRAME = "M15"      # M1/M5/M15/M30/H1/H4/D1/W1/MN1
    $env:MT5_TRADE_VOLUME = "0.01"
    $env:MT5_FAST_PERIOD = "5"
    $env:MT5_SLOW_PERIOD = "20"
    $env:MT5_MAX_OPEN_POSITIONS = "2"
    $env:MT5_DAILY_LOSS_LIMIT = "100"
    $env:MT5_HISTORY_BAR_COUNT = "2000"

Run (from the repository root, with the venv active):
    python scripts\\manual\\run_live_strategy.py

Stop any time with Ctrl+C -- it disconnects cleanly and does not leave the
strategy running unattended after the process exits.
"""

from __future__ import annotations

import asyncio
import os
import sys


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
    from core.interfaces.events import ConnectionStateChanged, OrderFilled, OrderRejected
    from core.interfaces.types import Symbol, Timeframe
    from core.interfaces.validation import ValidationReport
    from live_trading.runner import LiveRunner, LiveRunnerConfig, LiveRunnerError

    login = int(_require_env("MT5_LOGIN"))
    password = _require_env("MT5_PASSWORD")
    server = _require_env("MT5_SERVER")
    symbol_name = _require_env("MT5_TRADE_SYMBOL")
    symbol_suffix = os.environ.get("MT5_SYMBOL_SUFFIX", "")
    timeframe_name = os.environ.get("MT5_TRADE_TIMEFRAME", "M15")

    try:
        timeframe = Timeframe(timeframe_name)
    except ValueError:
        valid = ", ".join(t.value for t in Timeframe)
        print(
            f"Invalid MT5_TRADE_TIMEFRAME '{timeframe_name}'. Valid values: {valid}",
            file=sys.stderr,
        )
        sys.exit(1)

    config = LiveRunnerConfig(
        symbol=Symbol(name=symbol_name),
        timeframe=timeframe,
        fast_period=int(os.environ.get("MT5_FAST_PERIOD", "5")),
        slow_period=int(os.environ.get("MT5_SLOW_PERIOD", "20")),
        volume=float(os.environ.get("MT5_TRADE_VOLUME", "0.01")),
        max_open_positions=int(os.environ.get("MT5_MAX_OPEN_POSITIONS", "2")),
        daily_loss_limit=float(os.environ.get("MT5_DAILY_LOSS_LIMIT", "100")),
        history_bar_count=int(os.environ.get("MT5_HISTORY_BAR_COUNT", "2000")),
    )

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

    runner = LiveRunner(connector, config, event_bus)
    event_bus.subscribe(
        OrderFilled, lambda e: print(f"ORDER FILLED: {e.ack.correlation_id} @ {e.ack.fill_price}")
    )
    event_bus.subscribe(
        OrderRejected, lambda e: print(f"ORDER REJECTED: {e.ack.correlation_id}: {e.ack.reason}")
    )
    event_bus.subscribe(
        ConnectionStateChanged, lambda e: print(f"Connection state: {e.state.value}")
    )

    def _on_preflight_complete(report: ValidationReport, trade_returns: list[float]) -> None:
        if trade_returns:
            wins = sum(1 for r in trade_returns if r > 0)
            print(
                f"Trade history: {len(trade_returns)} trades, "
                f"{wins} winners ({100 * wins / len(trade_returns):.0f}%), "
                f"net {sum(trade_returns):+.5f}, "
                f"best {max(trade_returns):+.5f}, worst {min(trade_returns):+.5f}"
            )
        else:
            print("Trade history: 0 trades (no crossovers occurred in the fetched bars)")
        if report.passed:
            print(f"\nValidation PASSED for {config.symbol.canonical}. Starting live trading.")
            print("Press Ctrl+C to stop.\n")
        else:
            print(
                f"\nValidation FAILED ({report.failure_summary()}) -- refusing to trade live.",
                file=sys.stderr,
            )

    print(
        f"\nRunning pre-flight validation for {config.symbol.canonical} "
        f"({config.history_bar_count} historical {config.timeframe.value} bars)..."
    )

    try:
        await runner.run_forever(on_preflight_complete=_on_preflight_complete)
    except LiveRunnerError as exc:
        print(f"\n{exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"\nPre-flight failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        runner.stop()
    finally:
        await connector.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
