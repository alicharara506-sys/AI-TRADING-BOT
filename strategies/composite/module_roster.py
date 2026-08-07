"""The full AnalysisModule roster: every quant module this platform has
built, in one place, ready to register into a SignalEngine. Assembling this
list is the only thing this file does -- each module's own logic already
lives (and is already tested) in its own quant/ package; nothing here is
reimplemented.
"""

from __future__ import annotations

from core.interfaces.analysis import AnalysisModule
from core.interfaces.types import Timeframe
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from quant.fibonacci.extensions import FibonacciExtensionModule
from quant.multi_timeframe.alignment import HigherTimeframeAlignmentModule
from quant.price_action.smart_money_concepts import FairValueGapModule, LiquiditySweepModule
from quant.price_action.structure import MarketStructureModule
from quant.statistics.mean_reversion import AdfMeanReversionModule
from quant.statistics.seasonality import SeasonalityModule
from quant.technical_analysis.bands import (
    BollingerBandModule,
    DonchianBreakoutModule,
    KeltnerChannelModule,
)
from quant.technical_analysis.momentum import AdxTrendModule, MacdCrossoverModule
from quant.technical_analysis.volatility import AtrVolatilityBreakoutModule
from quant.technical_analysis.volume import OnBalanceVolumeModule
from quant.technical_analysis.volume_profile import VolumeProfileModule
from quant.technical_analysis.vwap import AnchoredVwapModule


def build_default_module_roster(
    *,
    swing_arm: int = 2,
    higher_timeframe: Timeframe | None = Timeframe.H4,
) -> list[AnalysisModule]:
    """Every AnalysisModule built across this platform's phases, each
    constructed with its own sensible defaults. Swing-based modules share
    `swing_arm` so they all read the same underlying market structure
    rather than each picking a different notion of "the last swing."

    HigherTimeframeAlignmentModule is included by default
    (`higher_timeframe=Timeframe.H4`) but will simply abstain (return no
    Evidence) until a caller populates
    `MarketContext.higher_timeframe_bars` -- the exact same "not enough
    data yet" graceful behavior every module here already has when its own
    lookback isn't satisfied, not a special case. Pass
    `higher_timeframe=None` to omit it from the roster entirely.
    """
    modules: list[AnalysisModule] = [
        AdfMeanReversionModule(),
        FibonacciConfluenceModule(swing_arm=swing_arm),
        FibonacciExtensionModule(swing_arm=swing_arm),
        EngulfingPatternModule(),
        MarketStructureModule(swing_arm=swing_arm),
        OnBalanceVolumeModule(),
        AtrVolatilityBreakoutModule(),
        MacdCrossoverModule(),
        AdxTrendModule(),
        BollingerBandModule(),
        KeltnerChannelModule(),
        DonchianBreakoutModule(),
        AnchoredVwapModule(swing_arm=swing_arm),
        VolumeProfileModule(),
        FairValueGapModule(),
        LiquiditySweepModule(swing_arm=swing_arm),
        SeasonalityModule(),
    ]
    if higher_timeframe is not None:
        modules.append(HigherTimeframeAlignmentModule(timeframe=higher_timeframe))
    return modules


__all__ = ["build_default_module_roster"]
