# Manual scripts

Scripts in this directory are meant to be run by a human on their own
machine against real infrastructure (a live MT4/MT5 terminal, a real
broker connection). They are **not** invoked by CI and are not part of
the automated test suite — the whole reason they exist is to touch things
CI cannot: a real terminal, real credentials, a real account.

- `mt5_connectivity_check.py` — read-only sanity check that
  `connectors.mt5.connector.MT5Connector` works against a real running MT5
  terminal via the real `MetaTrader5` pip package (Windows-only, must run
  on the same machine as the terminal). Connects, reads account state,
  symbol info, and open positions. Never places, modifies, or closes an
  order.
- `run_live_strategy.py` — runs a chosen `Strategy` (`MT5_STRATEGY`: one of
  `sma_crossover`, `fibonacci_elliott_wave`, or `signal_fusion` -- see
  `live_trading.strategy_selection`, `../../live_trading/strategy_selection.py`)
  against a real MT5 account through `live_trading.runner.LiveRunner`
  (`../../live_trading/runner.py`). Before it will place a single order, it
  fetches the account's own real historical bars and runs the strategy
  through the same backtest engine and Validation Pipeline described in the
  runbook below -- a strategy that doesn't pass is refused, not warned
  about. Every order that is placed still passes through the Risk Engine's
  gates and `FlipSafeExecutionEngine` (closes a stale opposite position
  first on hedging accounts, since MT5 hedging mode doesn't net an opposite
  order against an existing position the way a netting account does).
- `watch_signals.py` — the fallback when a broker's server itself refuses
  automated order submission (MT5 retcode 10026, "AutoTrading disabled by
  server" -- a permission this platform cannot grant or route around, seen
  in practice on a real SupremeFX-Server demo account). Runs the same chosen
  strategy against real live bars via `live_trading.signal_watcher.SignalWatcher`
  (`../../live_trading/signal_watcher.py`) and prints a `SIGNAL:` alert --
  with an ATR-based stop-loss/take-profit suggestion from
  `decision_engine.engine.DecisionEngine` -- whenever it fires, but never
  calls `submit_order`: the trade is placed by hand in the MT5 terminal.
- `run_dashboard_feed.py` — another read-only watcher (never calls
  `submit_order`), but instead of printing to the console it persists every
  signal (with its full agent-voting evidence and suggested SL/TP), account
  snapshot, and the underlying bars into a local SQLite database via
  `database.repository.SqliteSignalRepository`
  (`../../database/repository.py`). Pair it with `dashboard/app.py` below
  for a visual view of the same data.
- `dashboard/app.py` — a read-only Streamlit dashboard over the SQLite
  database `run_dashboard_feed.py` writes to. Never opens its own MT5
  connection. Shows account/connection state, the latest signal with its
  `SignalFusion` evidence rendered as an agent-voting table, a candlestick
  chart with Fibonacci retracement / Elliott Wave / volume-profile /
  market-structure overlays (`quant/technical_analysis/volume_profile.py`
  and the existing `quant/price_action/*` modules), a confidence gauge, a
  trade journal, and a performance tab. Needs the `dashboard` extra:
  `pip install -e ".[dashboard]"`, then
  `streamlit run scripts/manual/dashboard/app.py -- --db-path dashboard.db`.
- `fred_connectivity_check.py` — read-only sanity check that
  `macro_data.providers.fred.FredMacroProvider`
  (`../../macro_data/providers/fred.py`) works against the real FRED
  (Federal Reserve Economic Data) API. Fetches and prints a handful of
  recent observations for one series (default `T10Y2Y`, the 10Y-2Y
  Treasury yield spread). Needs a free `FRED_API_KEY`
  (https://fred.stlouisfed.org/docs/api/api_key.html) -- unlike the
  MT5-dependent scripts above, this one is cross-platform (no Windows/MT5
  terminal needed) since FRED is a plain HTTPS API. This is data-layer
  infrastructure only: nothing in this platform yet trades on it (see that
  module's docstring for why a directional AnalysisModule wasn't built
  alongside it).

## Available strategies

- `sma_crossover` (`strategies/simple/sma_crossover.py`) -- fast/slow
  moving-average crossover.
- `fibonacci_elliott_wave` (`strategies/pattern/fibonacci_elliott_wave.py`)
  -- fades a completed 5-wave Elliott impulse
  (`quant/price_action/elliott_wave.py`) whose wave 2/4 retracements and
  wave 3 extension fall within typical Fibonacci ranges. Deliberately
  implements only the *objective, mechanical* part of Elliott Wave theory
  (the three checkable structural rules plus Fibonacci ratio typicality),
  not the subjective wave-counting judgment real Elliott Wave analysis is
  notorious for disagreeing on -- see that module's docstring.
- `signal_fusion` (`strategies/composite/signal_fusion_strategy.py`) -- the
  full multi-module signal engine: every `AnalysisModule` this platform has
  built (`strategies/composite/module_roster.py` --  Fibonacci confluence/
  extension, Elliott Wave-adjacent market structure, candlestick patterns,
  ADF mean-reversion, ATR volatility breakout, OBV, MACD, ADX, Bollinger/
  Keltner/Donchian bands, anchored VWAP, volume profile, fair value gaps,
  liquidity sweeps, seasonality, and higher-timeframe alignment) runs on
  every bar, and `core.signal.fusion.SignalFusion` combines their Evidence
  into one `TradeSignal` -- the same log-odds-weighted consensus every
  quant-module integration test already proves works, now actually
  reachable from a live account. Configurable via
  `MT5_SIGNAL_FUSION_THRESHOLD` (default 0.6, must be in `[0.5, 1.0)`) and
  `MT5_HIGHER_TIMEFRAME` (default `H4`; set empty to disable the
  higher-timeframe module).

None of the three strategies is a validated, profitable strategy by
default. That's exactly what the pre-flight backtest checks against your
own account's real history, every single run, before either script will
place an order.

Before running anything here against a real account: read
[`docs/security/phase-14-review.md`](../../docs/security/phase-14-review.md)
for credential-handling guidance, and
[`docs/runbook/backtest-to-live.md`](../../docs/runbook/backtest-to-live.md)
for how this fits into the full backtest-to-live workflow.
