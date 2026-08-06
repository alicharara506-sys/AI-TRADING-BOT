from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics.hit_rate_store import HistoricalHitRateStore
from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe
from notifications.notifier import WebhookNotifier
from quant.candlesticks.patterns import EngulfingPatternModule
from reporting.performance_report import PerformanceReport
from tests.support.local_http_server import recording_http_server

_SYMBOL = Symbol(name="EURUSD")
_ENGULFING_BARS = [(1.10, 1.10, 1.08, 1.08), (1.07, 1.12, 1.07, 1.12)]
_RETURNS = [10, -5, 10, -5, 10, -5, 10, -5]


def _context() -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=max(o, h, low, c),
            low=min(o, h, low, c),
            close=c,
            volume=0.0,
        )
        for i, (o, h, low, c) in enumerate(_ENGULFING_BARS)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_hit_rate_store_changes_engulfing_module_confidence() -> None:
    """Phase 13 exit criteria, part 1: an EngulfingPatternModule backed by a
    HistoricalHitRateStore with real recorded outcomes emits a materially
    different confidence than the same module with no store -- proving the
    hit-rate store is actually wired into the signal path, not just present
    alongside it.
    """
    baseline = EngulfingPatternModule().analyze(_context())
    assert baseline[0].confidence == pytest.approx(1.0)
    assert baseline[0].rationale["confidence_source"] == "geometric"

    store = HistoricalHitRateStore(min_samples=3)
    for won in (True, True, False):
        store.record_outcome("engulfing_pattern", "EURUSD", won=won)

    historical = EngulfingPatternModule(hit_rate_store=store).analyze(_context())
    assert historical[0].confidence == pytest.approx(2 / 3)
    assert historical[0].rationale["confidence_source"] == "historical_hit_rate"
    assert historical[0].confidence != baseline[0].confidence


async def test_performance_report_reaches_a_real_webhook() -> None:
    """Phase 13 exit criteria, part 2: a PerformanceReport built from real
    trade returns is rendered and delivered by WebhookNotifier to a genuine
    HTTP server -- not a mock -- and the server observes the exact rendered
    text.
    """
    report = PerformanceReport.from_returns("demo_strategy", _RETURNS)

    with recording_http_server(port=18590) as server:
        notifier = WebhookNotifier(f"http://127.0.0.1:{server.server.server_port}/")

        await notifier.send(f"Performance report: {report.strategy_name}", report.render())

        assert len(server.received) == 1
        delivered = server.received[0]
        assert delivered["subject"] == "Performance report: demo_strategy"
        assert delivered["body"] == report.render()
        assert "Sharpe: 0.31" in delivered["body"]
