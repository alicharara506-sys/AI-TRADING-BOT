"""Ties a real MT5 connector to a strategy through the same Risk Engine,
Strategy Engine, and Validation Pipeline the rest of this platform uses --
see docs/runbook/backtest-to-live.md for the full wiring this package
automates, and live_trading/runner.py::LiveRunner for the entry point.
"""

from __future__ import annotations
