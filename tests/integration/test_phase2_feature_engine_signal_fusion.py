from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.price_action.smart_money_concepts import FairValueGapModule, LiquiditySweepModule
from quant.statistics.seasonality import SeasonalityModule
from quant.technical_analysis.bands import (
    BollingerBandModule,
    DonchianBreakoutModule,
    KeltnerChannelModule,
)
from quant.technical_analysis.momentum import AdxTrendModule, MacdCrossoverModule
from quant.technical_analysis.volume_profile import VolumeProfileModule
from quant.technical_analysis.vwap import AnchoredVwapModule

_SYMBOL = Symbol(name="EURUSD")
_BASE_MONDAY = datetime(2026, 1, 5, tzinfo=UTC)


def _context() -> MarketContext:
    # 40 days of small, symmetric oscillation (builds up band/ADX/seasonality
    # history without itself trending), followed by one large bullish
    # displacement day that breaks well above every band/channel built from
    # the quiet period.
    bars: list[Bar] = []
    price = 10.0
    for i in range(40):
        timestamp = _BASE_MONDAY + timedelta(days=i)
        move = 0.02 if i % 2 == 0 else -0.02
        open_, close = price, price + move
        bars.append(
            Bar(
                symbol=_SYMBOL,
                timeframe=Timeframe.D1,
                timestamp=timestamp,
                open=open_,
                high=max(open_, close) + 0.03,
                low=min(open_, close) - 0.03,
                close=close,
                volume=100.0 + 5 * i,
            )
        )
        price = close

    breakout_open = price
    breakout_close = price + 2.0
    bars.append(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.D1,
            timestamp=_BASE_MONDAY + timedelta(days=40),
            open=breakout_open,
            high=breakout_close + 0.1,
            low=breakout_open - 0.05,
            close=breakout_close,
            volume=500.0,
        )
    )
    return MarketContext(symbol=_SYMBOL, bars=tuple(bars))


def test_phase2_feature_engine_modules_compose_through_unmodified_signal_fusion() -> None:
    """Every module built in the Phase 2 "Feature Engine Tier 1" pass --
    momentum (MACD, ADX), bands (Bollinger, Keltner, Donchian), VWAP, volume
    profile, Smart Money Concepts (fair value gaps, liquidity sweeps), and
    seasonality -- registers into the exact same SignalEngine/SignalFusion
    Phase 7/11 already built, with zero changes needed to
    core/signal/fusion.py. On a clean breakout day, most fire (several
    disagreeing, e.g. Bollinger's mean-reversion read against the trend
    breakout the others see) and SignalFusion still correctly reaches a
    confident LONG consensus -- the same "conflicting evidence, correct
    outcome" property the Phase 11 roster test already demonstrates.
    """
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(
        MacdCrossoverModule(fast_period=5, slow_period=10, signal_period=3, atr_period=5)
    )
    engine.register_module(AdxTrendModule(period=5, trend_threshold=20.0))
    engine.register_module(BollingerBandModule(period=20, num_std=2.0))
    engine.register_module(KeltnerChannelModule(period=20, atr_period=10, multiplier=2.0))
    engine.register_module(DonchianBreakoutModule(period=20))
    engine.register_module(AnchoredVwapModule(swing_arm=2, atr_period=10))
    engine.register_module(VolumeProfileModule(bins=10, lookback=40))
    engine.register_module(FairValueGapModule(lookback=20))
    engine.register_module(LiquiditySweepModule(swing_arm=2))
    engine.register_module(
        SeasonalityModule(
            group_by="weekday", min_samples=5, min_mean_return=0.0001, scale_return=0.01
        )
    )

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.5

    # AdxTrendModule and FairValueGapModule correctly abstain (the quiet
    # oscillation never clears ADX's trend threshold, and no fair value gap
    # forms in the setup); everything else contributes, including two
    # modules that dissent (Bollinger reads the breakout as overextended,
    # volume profile reads it as trading above its own value area) without
    # preventing the correct LONG consensus.
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {
        "macd_crossover",
        "bollinger_band_reversion",
        "keltner_channel_breakout",
        "donchian_breakout",
        "anchored_vwap",
        "volume_profile",
        "liquidity_sweep",
        "seasonality",
    }
    dissenting = {
        item.source_module for item in signal.evidence if item.direction == Direction.SHORT
    }
    assert dissenting == {"bollinger_band_reversion", "volume_profile"}

    record = engine.history()[0]
    explanation = record.explain()
    for module_name in contributing:
        assert module_name in explanation
