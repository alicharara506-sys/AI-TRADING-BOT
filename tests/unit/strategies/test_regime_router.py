from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.interfaces.types import Bar, Direction, Evidence, MarketContext, Symbol, Timeframe
from core.signal.fusion import SignalFusion
from strategies.regime_router import (
    HIGH_VOL_ATR_MULTIPLE,
    HIGH_VOL_RISK_MULTIPLIER,
    MEAN_REVERT_MAX_CONFIDENCE,
    RegimeAwareStrategyRouter,
)

_SYMBOL = Symbol(name="EURUSD")
_BAR = Bar(
    symbol=_SYMBOL,
    timeframe=Timeframe.M1,
    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    open=1.0,
    high=1.0,
    low=1.0,
    close=1.0,
)


class _FakeModule:
    def __init__(self, name: str, evidence: list[Evidence]) -> None:
        self.name = name
        self._evidence = evidence

    def analyze(self, context: MarketContext) -> list[Evidence]:
        return list(self._evidence)


def _context() -> MarketContext:
    return MarketContext(symbol=_SYMBOL, bars=(_BAR,))


def _router(
    modules: list[_FakeModule], *, directional: str | None, volatility: str | None
) -> RegimeAwareStrategyRouter:
    return RegimeAwareStrategyRouter(
        modules,  # type: ignore[arg-type]
        SignalFusion(threshold=0.5),
        directional_regime_fn=lambda _bars: directional,  # type: ignore[arg-type,return-value]
        volatility_regime_fn=lambda _bars: volatility,  # type: ignore[arg-type,return-value]
    )


def test_no_regime_leaves_confidence_unchanged() -> None:
    modules = [
        _FakeModule("adx_trend", [Evidence("adx_trend", Direction.LONG, confidence=0.6)])
    ]
    router = _router(modules, directional=None, volatility=None)

    routed = router.evaluate(_context())

    assert routed.signal is not None
    assert routed.signal.combined_confidence == pytest.approx(0.6)
    assert routed.risk_adjustment.risk_multiplier == pytest.approx(1.0)
    assert routed.risk_adjustment.atr_multiple is None


def test_trend_regime_boosts_listed_modules_and_leaves_others_alone() -> None:
    modules = [
        _FakeModule("adx_trend", [Evidence("adx_trend", Direction.LONG, confidence=0.4)]),
        _FakeModule(
            "adf_mean_reversion",
            [Evidence("adf_mean_reversion", Direction.LONG, confidence=0.6)],
        ),
    ]
    router = _router(modules, directional="trend_up", volatility=None)

    routed = router.evaluate(_context())

    assert routed.directional_regime == "trend_up"
    assert routed.signal is not None
    # adx_trend is boosted 1.25x (0.4 -> 0.5) before fusion; adf_mean_reversion
    # is untouched (0.6, not in TREND_WEIGHT_MULTIPLIERS). Both agree LONG, so
    # combined confidence must exceed the unboosted-adx baseline of fusing
    # 0.4 and 0.6 -- proving the boost actually changed the fused result.
    unboosted_fusion = SignalFusion(threshold=0.5).fuse(
        _SYMBOL,
        [
            Evidence("adx_trend", Direction.LONG, confidence=0.4),
            Evidence("adf_mean_reversion", Direction.LONG, confidence=0.6),
        ],
    )
    assert unboosted_fusion is not None
    assert routed.signal.combined_confidence > unboosted_fusion.combined_confidence


def test_mean_revert_regime_caps_confidence_even_for_unboosted_modules() -> None:
    evidence = Evidence("some_other_module", Direction.SHORT, confidence=0.99)
    modules = [_FakeModule("some_other_module", [evidence])]
    router = _router(modules, directional="mean_revert", volatility=None)

    routed = router.evaluate(_context())

    assert routed.signal is not None
    assert routed.signal.combined_confidence <= MEAN_REVERT_MAX_CONFIDENCE + 1e-9


def test_mean_revert_regime_boosts_adf_module_before_capping() -> None:
    evidence = Evidence("adf_mean_reversion", Direction.LONG, confidence=0.5)
    modules = [_FakeModule("adf_mean_reversion", [evidence])]
    router = _router(modules, directional="mean_revert", volatility=None)

    routed = router.evaluate(_context())

    assert routed.signal is not None
    # 0.5 * 1.25 = 0.625, well under the 0.75 cap -- the boost must have
    # actually applied, not just been clipped straight to the cap.
    assert routed.signal.combined_confidence == pytest.approx(0.625)


def test_high_volatility_regime_reduces_risk_and_widens_stop() -> None:
    router = _router([], directional=None, volatility="high")

    routed = router.evaluate(_context())

    assert routed.volatility_regime == "high"
    assert routed.risk_adjustment.risk_multiplier == pytest.approx(HIGH_VOL_RISK_MULTIPLIER)
    assert routed.risk_adjustment.atr_multiple == pytest.approx(HIGH_VOL_ATR_MULTIPLE)


def test_no_evidence_produces_no_signal() -> None:
    router = _router([], directional="trend_up", volatility=None)

    routed = router.evaluate(_context())

    assert routed.signal is None
