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

Before running anything here against a real account: read
[`docs/security/phase-14-review.md`](../../docs/security/phase-14-review.md)
for credential-handling guidance, and
[`docs/runbook/backtest-to-live.md`](../../docs/runbook/backtest-to-live.md)
for how this fits into the full backtest-to-live workflow.
