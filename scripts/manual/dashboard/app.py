"""Read-only Streamlit dashboard over the SQLite database
scripts/manual/run_dashboard_feed.py writes to. Never opens its own MT5
connection -- every panel is a query against the same database file, so
this can run on a different machine, or just a second terminal window,
from the feed script.

Setup (PowerShell, same venv as the feed script):
    pip install -e ".[dashboard]"

Run (from the repository root, feed script already running separately):
    streamlit run scripts\\manual\\dashboard\\app.py -- \
        --db-path dashboard.db --symbol EURUSD --timeframe M15

`--db-path`/`--symbol`/`--timeframe` all default to the same values
run_dashboard_feed.py uses by default (MT5_DASHBOARD_DB_PATH, the required
MT5_TRADE_SYMBOL you set for the feed script, and M15) -- pass them
explicitly here if you configured the feed script differently.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe
from database.models import RecordedBar
from database.repository import SqliteSignalRepository
from quant.price_action.elliott_wave import find_five_wave_impulse
from quant.price_action.structure import MarketStructureModule
from quant.price_action.swings import find_last_swings
from quant.technical_analysis.volume_profile import compute_volume_profile
from reporting.performance_report import PerformanceReport

_FIB_RATIOS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="dashboard.db")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="M15")
    # Streamlit's own CLI args are stripped before `--`; anything after it
    # lands in sys.argv unchanged, so unknown args are ignored rather than
    # raising -- avoids fighting Streamlit's own arg parser.
    args, _unknown = parser.parse_known_args()
    return args


@st.cache_resource
def _repository(db_path: str) -> SqliteSignalRepository:
    return SqliteSignalRepository(f"sqlite:///{db_path}")


def _recorded_bars_to_core_bars(
    symbol: Symbol, timeframe: Timeframe, rows: list[RecordedBar]
) -> tuple[Bar, ...]:
    return tuple(
        Bar(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in rows
    )


def _render_account_panel(repository: SqliteSignalRepository) -> None:
    st.subheader("Account")
    snapshot = repository.latest_account_snapshot()
    if snapshot is None:
        st.info("No account snapshot recorded yet. Is run_dashboard_feed.py running?")
        return
    age_seconds = (datetime.utcnow() - snapshot.timestamp).total_seconds()
    cols = st.columns(5)
    cols[0].metric("Balance", f"{snapshot.balance:,.2f} {snapshot.currency}")
    cols[1].metric("Equity", f"{snapshot.equity:,.2f} {snapshot.currency}")
    cols[2].metric("Margin", f"{snapshot.margin:,.2f}")
    cols[3].metric("Free margin", f"{snapshot.free_margin:,.2f}")
    cols[4].metric(
        "Margin level", f"{snapshot.margin_level:,.1f}%" if snapshot.margin_level else "n/a"
    )
    status = "LIVE" if age_seconds < 120 else "STALE"
    st.caption(
        f"{status} -- last snapshot {age_seconds:.0f}s ago ({snapshot.timestamp.isoformat()})"
    )


def _render_signal_panel(repository: SqliteSignalRepository, symbol: str) -> None:
    st.subheader(f"Latest signal: {symbol}")
    signal = repository.latest_signal(symbol)
    if signal is None:
        st.info(f"No signal recorded yet for {symbol}.")
        return

    cols = st.columns(6)
    cols[0].metric("Direction", signal.direction.upper())
    cols[1].metric("Entry", f"{signal.entry_price:.5f}" if signal.entry_price else "n/a")
    cols[2].metric("Stop-loss", f"{signal.stop_loss:.5f}" if signal.stop_loss else "n/a")
    cols[3].metric("Take-profit", f"{signal.take_profit:.5f}" if signal.take_profit else "n/a")
    cols[4].metric("Confidence", f"{signal.confidence * 100:.0f}%")
    cols[5].metric("Uncertainty", signal.uncertainty)

    if signal.stop_loss and signal.take_profit and signal.entry_price:
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk > 0:
            atr_text = f"{signal.atr:.5f}" if signal.atr is not None else "n/a"
            st.caption(
                f"Strategy: {signal.strategy_name}  |  Risk/reward: 1:{reward / risk:.2f}  "
                f"|  ATR: {atr_text}"
            )

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=signal.confidence * 100,
            title={"text": "Combined confidence"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2ecc71" if signal.direction == "long" else "#e74c3c"},
                "steps": [
                    {"range": [0, 50], "color": "#2a2a2a"},
                    {"range": [50, 75], "color": "#3a3a3a"},
                    {"range": [75, 100], "color": "#4a4a4a"},
                ],
            },
        )
    )
    fig.update_layout(height=250, margin={"t": 40, "b": 10, "l": 20, "r": 20})
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Agent votes (SignalFusion evidence)**")
    evidence = json.loads(signal.evidence_json)
    if not evidence:
        st.caption("No evidence recorded.")
    else:
        st.dataframe(
            [
                {
                    "module": item["source_module"],
                    "direction": item["direction"],
                    "confidence": round(item["confidence"], 3),
                    "rationale": json.dumps(item["rationale"]),
                }
                for item in evidence
            ],
            width="stretch",
            hide_index=True,
        )


def _render_chart(repository: SqliteSignalRepository, symbol: str, timeframe: str) -> None:
    st.subheader("Price chart")
    rows = repository.list_recent_bars(symbol, timeframe, limit=500)
    if len(rows) < 10:
        st.info(
            f"Not enough recorded bars yet for {symbol} {timeframe} "
            f"({len(rows)} so far) -- the chart needs a few more to render."
        )
        return

    core_bars = _recorded_bars_to_core_bars(Symbol(name=symbol), Timeframe(timeframe), rows)
    context = MarketContext(symbol=Symbol(name=symbol), bars=core_bars)

    profile = compute_volume_profile(core_bars)
    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.85, 0.15],
        shared_yaxes=True,
        horizontal_spacing=0.01,
    )

    fig.add_trace(
        go.Candlestick(
            x=[row.timestamp for row in rows],
            open=[row.open for row in rows],
            high=[row.high for row in rows],
            low=[row.low for row in rows],
            close=[row.close for row in rows],
            name=symbol,
        ),
        row=1,
        col=1,
    )

    low_index, high_index = find_last_swings(core_bars, arm=2)
    if low_index is not None and high_index is not None and low_index != high_index:
        impulse_up = low_index < high_index
        swing_low, swing_high = core_bars[low_index].low, core_bars[high_index].high
        leg_range = swing_high - swing_low
        if leg_range > 0:
            x_range = [rows[0].timestamp, rows[-1].timestamp]
            for ratio in _FIB_RATIOS:
                level = (
                    swing_high - ratio * leg_range
                    if impulse_up
                    else swing_low + ratio * leg_range
                )
                fig.add_trace(
                    go.Scatter(
                        x=x_range,
                        y=[level, level],
                        mode="lines",
                        line={"color": "rgba(255,193,7,0.4)", "width": 1, "dash": "dot"},
                        name=f"fib {ratio:.3f}",
                        showlegend=False,
                    ),
                    row=1,
                    col=1,
                )

    impulse = find_five_wave_impulse(core_bars, swing_arm=2)
    if impulse is not None:
        wave_x = [core_bars[i].timestamp for i in impulse.indices]
        fig.add_trace(
            go.Scatter(
                x=wave_x,
                y=list(impulse.pivots),
                mode="lines+markers+text",
                text=["0", "1", "2", "3", "4", "5"],
                textposition="top center",
                line={"color": "#00bcd4", "width": 2},
                name="Elliott impulse",
            ),
            row=1,
            col=1,
        )

    structure_evidence = MarketStructureModule(swing_arm=2).analyze(context)
    for item in structure_evidence:
        level = item.rationale.get("level")
        event = item.rationale.get("event", "structure")
        if level is not None:
            fig.add_hline(
                y=level,
                line={"color": "#ff5252", "width": 1, "dash": "dash"},
                annotation_text=event,
                row=1,
                col=1,
            )

    if profile is not None:
        fig.add_trace(
            go.Bar(
                x=[level.volume for level in profile.levels],
                y=[level.price for level in profile.levels],
                orientation="h",
                marker={"color": "rgba(0,188,212,0.5)"},
                name="volume profile",
                showlegend=False,
            ),
            row=1,
            col=2,
        )
        fig.add_hline(
            y=profile.point_of_control,
            line={"color": "#00bcd4", "width": 1},
            row=1,
            col=1,
        )

    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        margin={"t": 20, "b": 20, "l": 20, "r": 20},
        legend={"orientation": "h"},
    )
    st.plotly_chart(fig, width="stretch")


def _render_trade_journal(repository: SqliteSignalRepository) -> None:
    st.subheader("Trade journal")
    trades = repository.list_trades()
    if not trades:
        st.info("No filled trades recorded yet.")
        return
    st.dataframe(
        [
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "side": t.side,
                "volume": t.volume,
                "open_price": t.open_price,
                "close_price": t.close_price,
                "open_time": t.open_time,
                "close_time": t.close_time,
                "profit": t.profit,
            }
            for t in trades
        ],
        width="stretch",
        hide_index=True,
    )


def _render_performance(repository: SqliteSignalRepository, strategy_name: str) -> None:
    st.subheader("Performance")
    trades = repository.list_trades()
    if len(trades) < 5:
        st.info(
            f"Only {len(trades)} recorded trade(s) so far -- "
            "not enough for performance metrics yet."
        )
        return
    returns = [t.profit for t in trades]
    report = PerformanceReport.from_returns(strategy_name, returns)
    cols = st.columns(4)
    cols[0].metric("Trades", report.trade_count)
    cols[1].metric("Total return", f"{report.total_return:+.2f}")
    cols[2].metric("Win-weighted Sharpe", f"{report.sharpe_ratio:.2f}")
    cols[3].metric("Max drawdown", f"{report.max_drawdown:.2f}")
    cols = st.columns(4)
    cols[0].metric("Profit factor", f"{report.profit_factor:.2f}")
    cols[1].metric("Expectancy", f"{report.expectancy:.2f}")
    cols[2].metric("Sortino", f"{report.sortino_ratio:.2f}")
    cols[3].metric("Calmar", f"{report.calmar_ratio:.2f}")


def main() -> None:
    args = _parse_args()
    st.set_page_config(page_title="AI Trading Bot -- Dashboard", layout="wide")
    st.title("AI Trading Bot -- Live Signal Dashboard")
    st.caption(
        f"Reading {args.db_path} -- written by run_dashboard_feed.py. "
        "Read-only: this page never places, modifies, or closes an order."
    )

    repository = _repository(args.db_path)

    _render_account_panel(repository)
    st.divider()
    _render_signal_panel(repository, args.symbol)
    st.divider()
    _render_chart(repository, args.symbol, args.timeframe)
    st.divider()

    tab_journal, tab_performance = st.tabs(["Trade journal", "Performance"])
    with tab_journal:
        _render_trade_journal(repository)
    with tab_performance:
        latest_signal = repository.latest_signal(args.symbol)
        strategy_name = latest_signal.strategy_name if latest_signal else "unknown"
        _render_performance(repository, strategy_name)

    if st.sidebar.checkbox("Auto-refresh every 5s", value=False):
        time.sleep(5)
        st.rerun()


main()
