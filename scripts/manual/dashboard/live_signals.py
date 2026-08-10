"""Royal-Pips-style live signal tracker cards, resolved-outcome analytics,
and closing-note banners for the read-only Streamlit dashboard (app.py) --
built entirely from Plotly/Streamlit (both already declared [dashboard]
dependencies) and this platform's own OutcomeAnalytics. No new dependency,
no external API call.

CLOSE/Edit-note/reactions write directly through SqliteSignalRepository
(the same repository app.py already reads from), reconstructing a
SignalOutcome from the persisted RecordedOutcome row -- there is no live
EventBus subscription here (this stays a database-only script, exactly
like the rest of app.py), so these writes are simple, one-shot row
updates, not new live tracking logic.
"""

from __future__ import annotations

import json
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from analytics.outcome_analytics import OutcomeAnalytics
from core.interfaces.types import Direction
from database.models import RecordedOutcome
from database.repository import SqliteSignalRepository
from live_tracking.types import HitTarget, OutcomeStatus, SignalOutcome

_REACTION_EMOJIS = ("🔥", "❤️", "😎", "💎")
_STATUS_LABELS = {
    "pending": "PENDING",
    "active": "ACTIVE",
    "tp1_hit": "TP1 HIT",
    "tp2_hit": "TP2 HIT",
    "tp3_hit": "TP3 HIT",
    "sl_hit": "SL HIT",
    "expired": "EXPIRED",
    "closed_manual": "CLOSED",
}


def _pips(row: RecordedOutcome, price: float) -> float:
    direction = 1.0 if row.direction == "long" else -1.0
    return direction * (price - row.entry_price) / row.pip_size


def _target_hit(row: RecordedOutcome, price: float) -> bool:
    """A target counts as hit if price ever reached it, read off the
    outcome's own recorded highest_pips excursion -- correct even after a
    later reversal collapses `status` to sl_hit/closed_manual, unlike
    reading status alone (live_tracking/types.py's OutcomeStatus docstring:
    TP1_HIT/TP2_HIT are not terminal, and a later SL hit overwrites status
    without erasing the fact that TP1 was actually reached first).
    """
    return row.highest_pips >= _pips(row, price) - 1e-9


def _to_signal_outcome(row: RecordedOutcome) -> SignalOutcome:
    return SignalOutcome(
        id=row.id,
        symbol=row.symbol,
        direction=Direction(row.direction),
        strategy_name=row.strategy_name,
        entry_price=row.entry_price,
        stop_loss=row.stop_loss,
        take_profit_1=row.take_profit_1,
        pip_size=row.pip_size,
        timestamp_generated=row.timestamp_generated,
        score_at_generation=row.score_at_generation,
        uncertainty_at_generation=row.uncertainty_at_generation,
        take_profit_2=row.take_profit_2,
        take_profit_3=row.take_profit_3,
        trigger_price=row.trigger_price,
        regime_at_generation=row.regime_at_generation,
        sentiment_at_generation=row.sentiment_at_generation,
        ml_probability_at_generation=row.ml_probability_at_generation,
        status=OutcomeStatus(row.status),
        highest_pips=row.highest_pips,
        lowest_pips=row.lowest_pips,
        final_pips=row.final_pips,
        achieved_risk_reward=row.achieved_risk_reward,
        timestamp_triggered=row.timestamp_triggered,
        timestamp_resolved=row.timestamp_resolved,
        hit_target=HitTarget(row.hit_target) if row.hit_target else None,
        user_note=row.user_note,
        user_reactions=json.loads(row.user_reactions_json),
    )


def _price_tracker_figure(row: RecordedOutcome, live_price: float) -> go.Figure:
    targets = [
        (name, price)
        for name, price in (
            ("TP1", row.take_profit_1),
            ("TP2", row.take_profit_2),
            ("TP3", row.take_profit_3),
        )
        if price is not None
    ]
    farthest_tp = targets[-1][1]
    span = farthest_tp - row.stop_loss

    def norm(price: float) -> float:
        return 0.5 if span == 0 else (price - row.stop_loss) / span

    fig = go.Figure()
    entry_x = norm(row.entry_price)
    fig.add_shape(type="line", x0=0, x1=entry_x, y0=0, y1=0, line={"color": "#e74c3c", "width": 10})
    fig.add_shape(type="line", x0=entry_x, x1=1, y0=0, y1=0, line={"color": "#2ecc71", "width": 10})

    marker_x = [0.0, entry_x]
    marker_text = ["SL", "Entry"]
    marker_color = ["#e74c3c", "#f1c40f"]
    for name, price in targets:
        marker_x.append(norm(price))
        hit = _target_hit(row, price)
        marker_text.append(f"{name} ✓" if hit else name)
        marker_color.append("#2ecc71" if hit else "#95a5a6")

    fig.add_trace(
        go.Scatter(
            x=marker_x,
            y=[0] * len(marker_x),
            mode="markers+text",
            text=marker_text,
            textposition="top center",
            marker={"size": 14, "color": marker_color, "line": {"width": 1, "color": "white"}},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[norm(live_price)],
            y=[0],
            mode="markers",
            marker={"size": 20, "color": "#3498db", "line": {"width": 2, "color": "white"}},
            showlegend=False,
        )
    )
    fig.update_xaxes(visible=False, range=[-0.08, 1.08])
    fig.update_yaxes(visible=False, range=[-1, 1])
    fig.update_layout(height=130, margin={"t": 30, "b": 10, "l": 20, "r": 20}, showlegend=False)
    return fig


def render_closing_note_banner(row: RecordedOutcome) -> None:
    if row.timestamp_resolved is None:
        return
    pips = row.final_pips or 0.0
    if row.status == "sl_hit":
        st.error(f"\U0001f6d1 SL HIT at {row.stop_loss:.5f} ({pips:+.1f} pips)")
    elif row.status == "expired":
        st.warning("⏱️ EXPIRED — trigger never reached")
    elif row.status == "closed_manual":
        st.info(f"Closed manually ({pips:+.1f} pips)")
    else:
        target_price = {
            "tp1_hit": row.take_profit_1,
            "tp2_hit": row.take_profit_2,
            "tp3_hit": row.take_profit_3,
        }.get(row.status)
        label = row.hit_target or row.status.replace("_hit", "").upper()
        price_text = f"{target_price:.5f}" if target_price is not None else "n/a"
        st.success(f"\U0001f3af {label} HIT at {price_text} ({pips:+.1f} pips)")


def _share_text(row: RecordedOutcome, live_price: float) -> str:
    lines = [
        f"{row.symbol} · {row.direction.upper()}",
        f"Entry {row.entry_price:.5f}  |  Live {live_price:.5f}  "
        f"({_pips(row, live_price):+.1f} pips)",
        f"SL {row.stop_loss:.5f}  |  TP1 {row.take_profit_1:.5f}",
    ]
    if row.take_profit_2 is not None:
        lines.append(f"TP2 {row.take_profit_2:.5f}")
    if row.take_profit_3 is not None:
        lines.append(f"TP3 {row.take_profit_3:.5f}")
    lines.append(f"Status: {_STATUS_LABELS.get(row.status, row.status)}")
    return "\n".join(lines)


def _close_manual(repository: SqliteSignalRepository, row: RecordedOutcome, price: float) -> None:
    outcome = _to_signal_outcome(row)
    outcome.status = OutcomeStatus.CLOSED_MANUAL
    outcome.hit_target = None
    outcome.timestamp_resolved = datetime.utcnow()
    outcome.final_pips = _pips(row, price)
    outcome.highest_pips = max(outcome.highest_pips, outcome.final_pips)
    outcome.lowest_pips = min(outcome.lowest_pips, outcome.final_pips)
    risk_pips = abs(row.entry_price - row.stop_loss) / row.pip_size
    outcome.achieved_risk_reward = outcome.final_pips / risk_pips if risk_pips > 0 else None
    repository.save_outcome(outcome)


def render_live_signal_card(repository: SqliteSignalRepository, row: RecordedOutcome) -> None:
    with st.container(border=True):
        header = st.columns([3, 1, 1, 1])
        header[0].markdown(f"### {row.symbol} · {row.direction.upper()}")
        header[1].metric("Score", f"{row.score_at_generation * 100:.0f}")
        header[2].metric("Confidence", row.uncertainty_at_generation.upper())
        header[3].markdown(f"**{_STATUS_LABELS.get(row.status, row.status)}**")

        render_closing_note_banner(row)

        samples = repository.list_outcome_samples(row.id, limit=1)
        live_price = samples[-1].price if samples else row.entry_price

        st.plotly_chart(
            _price_tracker_figure(row, live_price), width="stretch", key=f"tracker_{row.id}"
        )

        metric_cols = st.columns(2)
        metric_cols[0].metric("Entry level", f"{row.entry_price:.5f}")
        metric_cols[1].metric("Live price", f"{live_price:.5f}")

        for name, price in (
            ("TP1", row.take_profit_1),
            ("TP2", row.take_profit_2),
            ("TP3", row.take_profit_3),
        ):
            if price is None:
                continue
            hit = _target_hit(row, price)
            icon = "✅" if hit else "⬜"
            badge = "HIT" if hit else "PENDING"
            pips_text = f"({_pips(row, price):+.1f} pips)"
            st.markdown(f"{icon} **{name}**  {price:.5f}  {pips_text}  `{badge}`")

        st.markdown(
            f"\U0001f6e1️ **Stop Loss**  {row.stop_loss:.5f}  "
            f"({_pips(row, row.stop_loss):+.1f} pips)"
        )

        footer = st.columns(2)
        if row.timestamp_resolved is None:
            footer[0].markdown(f":green[**LIVE {_pips(row, live_price):+.1f} pips**]")
        else:
            footer[0].markdown(f":orange[**SAVED {(row.final_pips or 0.0):+.1f} pips**]")

        actions = st.columns(3)
        if row.timestamp_resolved is None and actions[0].button("Close", key=f"close_{row.id}"):
            _close_manual(repository, row, live_price)
            st.rerun()

        with actions[1].popover("Edit"):
            note = st.text_area("Note", value=row.user_note or "", key=f"note_{row.id}")
            if st.button("Save note", key=f"save_note_{row.id}"):
                repository.set_user_note(row.id, note)
                st.rerun()

        with actions[2].popover("Share"):
            st.code(_share_text(row, live_price))

        reaction_cols = st.columns(len(_REACTION_EMOJIS))
        for index, emoji in enumerate(_REACTION_EMOJIS):
            if reaction_cols[index].button(emoji, key=f"react_{index}_{row.id}"):
                repository.add_reaction(row.id, emoji)
                st.rerun()


def render_live_signals_tab(repository: SqliteSignalRepository, symbol: str) -> None:
    st.subheader("Live signal tracker")
    filter_choice = st.radio(
        "Show", ["ALL", "ACTIVE", "CLOSED"], horizontal=True, key="live_signal_filter"
    )
    rows = repository.list_outcomes(symbol=symbol, limit=50)
    if filter_choice == "ACTIVE":
        rows = [row for row in rows if row.timestamp_resolved is None]
    elif filter_choice == "CLOSED":
        rows = [row for row in rows if row.timestamp_resolved is not None]

    if not rows:
        st.info(f"No tracked signals yet for {symbol}. Is SignalLifecycleTracker running?")
        return

    for row in rows:
        render_live_signal_card(repository, row)


def _kelly_fraction(win_rate: float, avg_win_loss_ratio: float) -> float | None:
    """Kelly Criterion optimal fraction: K = W - (1-W)/R. Info-only display
    figure -- nothing in this platform sizes a position off this value
    (RiskEngine's own sizing is unrelated and unaffected). None when the
    win/loss ratio is non-positive (nothing meaningful to divide by)."""
    if avg_win_loss_ratio <= 0:
        return None
    return win_rate - (1.0 - win_rate) / avg_win_loss_ratio


def render_outcome_analytics_tab(repository: SqliteSignalRepository) -> None:
    st.subheader("Outcome analytics")
    regime_choice = st.radio(
        "Regime",
        ["ALL", "TREND_UP", "TREND_DOWN", "MEAN_REVERT"],
        horizontal=True,
        key="regime_filter",
    )

    rows = repository.list_outcomes(limit=2000)
    outcomes = [_to_signal_outcome(row) for row in rows]
    if regime_choice != "ALL":
        outcomes = [
            outcome
            for outcome in outcomes
            if (outcome.regime_at_generation or "").upper() == regime_choice
        ]

    analytics = OutcomeAnalytics(outcomes)
    report = analytics.report()

    if report.resolved_count == 0:
        st.info("No resolved outcomes yet -- analytics need at least one closed signal.")
        return

    cols = st.columns(5)
    cols[0].metric("Win rate", f"{(report.win_rate or 0) * 100:.1f}%")
    cols[1].metric("Resolved", report.resolved_count)
    cols[2].metric("Expectancy", f"{(report.expectancy_pips or 0):+.1f} pips")
    cols[3].metric("Avg planned R:R", f"{(report.average_planned_risk_reward or 0):.2f}")
    cols[4].metric("Calibrated", "Yes" if report.is_calibrated else "No")

    if report.score_buckets:
        bucket_fig = go.Figure(
            go.Bar(
                x=[f"{bucket.lower:.0f}-{bucket.upper:.0f}" for bucket in report.score_buckets],
                y=[bucket.win_rate * 100 for bucket in report.score_buckets],
                text=[f"n={bucket.sample_count}" for bucket in report.score_buckets],
                marker={"color": "#2ecc71"},
            )
        )
        bucket_fig.update_layout(
            title="Win rate by score bucket",
            yaxis_title="Win rate %",
            height=300,
            margin={"t": 40, "b": 20, "l": 20, "r": 20},
        )
        st.plotly_chart(bucket_fig, width="stretch")

    equity_curve = analytics.equity_curve_pips()
    if equity_curve:
        equity_fig = go.Figure(go.Scatter(y=equity_curve, mode="lines", line={"color": "#3498db"}))
        equity_fig.update_layout(
            title="Equity curve (cumulative net pips)",
            height=300,
            margin={"t": 40, "b": 20, "l": 20, "r": 20},
        )
        st.plotly_chart(equity_fig, width="stretch")

    if report.win_rate_by_symbol:
        st.markdown("**Win rate by symbol**")
        st.dataframe(
            [
                {"symbol": symbol, "win_rate": f"{rate * 100:.1f}%"}
                for symbol, rate in report.win_rate_by_symbol.items()
            ],
            width="stretch",
            hide_index=True,
        )

    win_rate = report.win_rate
    avg_rr = report.average_achieved_risk_reward or report.average_planned_risk_reward
    if win_rate is not None and avg_rr is not None:
        kelly = _kelly_fraction(win_rate, avg_rr)
        if kelly is not None:
            st.caption(
                f"Kelly Criterion (info only): K = {win_rate:.2f} - "
                f"(1-{win_rate:.2f})/{avg_rr:.2f} = **{kelly * 100:.1f}%** of equity"
            )

    st.markdown("**Recent outcomes**")
    recent = sorted(rows, key=lambda r: r.timestamp_generated, reverse=True)[:20]
    st.dataframe(
        [
            {
                "symbol": row.symbol,
                "direction": row.direction,
                "status": _STATUS_LABELS.get(row.status, row.status),
                "final_pips": row.final_pips,
                "score": round(row.score_at_generation * 100, 1),
                "generated": row.timestamp_generated,
            }
            for row in recent
        ],
        width="stretch",
        hide_index=True,
    )


__all__ = [
    "render_closing_note_banner",
    "render_live_signal_card",
    "render_live_signals_tab",
    "render_outcome_analytics_tab",
]
