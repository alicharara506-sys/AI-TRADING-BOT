from __future__ import annotations

import pytest

from core.interfaces.types import Direction, Symbol, TradeSignal
from core.risk.sizing import FixedVolumeSizingModel


def _signal() -> TradeSignal:
    return TradeSignal(
        symbol=Symbol(name="EURUSD"),
        direction=Direction.LONG,
        combined_confidence=1.0,
        threshold=0.0,
        evidence=(),
    )


def test_returns_fixed_volume_regardless_of_equity() -> None:
    model = FixedVolumeSizingModel(0.2)

    assert model.size(_signal(), equity=1_000.0) == pytest.approx(0.2)
    assert model.size(_signal(), equity=1_000_000.0) == pytest.approx(0.2)


def test_rejects_non_positive_volume() -> None:
    with pytest.raises(ValueError):
        FixedVolumeSizingModel(0.0)
    with pytest.raises(ValueError):
        FixedVolumeSizingModel(-0.1)
