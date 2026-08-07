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
- `run_live_strategy.py` — runs a chosen `Strategy` (`MT5_STRATEGY`: either
  `sma_crossover` or `fibonacci_elliott_wave` -- see
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

Neither strategy is a validated, profitable strategy by default. That's
exactly what the pre-flight backtest checks against your own account's
real history, every single run, before either script will place an order.

Before running anything here against a real account: read
[`docs/security/phase-14-review.md`](../../docs/security/phase-14-review.md)
for credential-handling guidance, and
[`docs/runbook/backtest-to-live.md`](../../docs/runbook/backtest-to-live.md)
for how this fits into the full backtest-to-live workflow.
