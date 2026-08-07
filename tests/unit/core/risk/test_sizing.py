from __future__ import annotations

import pytest

from core.interfaces.types import Direction, Symbol, TradeSignal
from core.risk.sizing import FixedVolumeSizingModel, KellySizingModel, RiskPercentSizingModel


def _signal(symbol: str = "EURUSD") -> TradeSignal:
    return TradeSignal(
        symbol=Symbol(name=symbol),
        direction=Direction.LONG,
        combined_confidence=1.0,
        threshold=0.0,
        evidence=(),
    )


def test_returns_fixed_volume_regardless_of_equity() -> None:
    model = FixedVolumeSizingModel(0.2)

    assert model.size(_signal(), equity=1_000.0) == pytest.approx(0.2)
    assert model.size(_signal(), equity=1_000_000.0) == pytest.approx(0.2)


def test_fixed_volume_ignores_stop_distance() -> None:
    model = FixedVolumeSizingModel(0.2)

    assert model.size(_signal(), equity=1_000.0, stop_distance=0.005) == pytest.approx(0.2)


def test_rejects_non_positive_volume() -> None:
    with pytest.raises(ValueError):
        FixedVolumeSizingModel(0.0)
    with pytest.raises(ValueError):
        FixedVolumeSizingModel(-0.1)


# -- RiskPercentSizingModel ------------------------------------------------


def test_risk_percent_model_sizes_from_equity_and_stop_distance() -> None:
    model = RiskPercentSizingModel(0.02)

    size = model.size(_signal(), equity=10_000.0, stop_distance=0.005)

    # Risking 2% of 10,000 = 200; over a 0.005 stop distance = 40,000 units.
    assert size == pytest.approx(40_000.0)


def test_risk_percent_model_returns_zero_without_a_stop_distance() -> None:
    model = RiskPercentSizingModel(0.02)

    assert model.size(_signal(), equity=10_000.0) == 0.0
    assert model.size(_signal(), equity=10_000.0, stop_distance=0.0) == 0.0


def test_risk_percent_model_rejects_invalid_risk_percent() -> None:
    with pytest.raises(ValueError):
        RiskPercentSizingModel(0.0)
    with pytest.raises(ValueError):
        RiskPercentSizingModel(1.5)


# -- KellySizingModel --------------------------------------------------------


class _FakeStatistics:
    def __init__(
        self, *, win_rate: float | None, win_loss_ratio: float | None, sample_count: int
    ) -> None:
        self._win_rate = win_rate
        self._win_loss_ratio = win_loss_ratio
        self._sample_count = sample_count

    def win_rate(self, symbol: str) -> float | None:
        return self._win_rate

    def win_loss_ratio(self, symbol: str) -> float | None:
        return self._win_loss_ratio

    def sample_count(self, symbol: str) -> int:
        return self._sample_count


def test_kelly_model_sizes_from_the_kelly_fraction() -> None:
    # f* = 0.55 - 0.45/1.5 = 0.25, under the 0.5 cap used here so it sizes
    # from the raw Kelly fraction, not the cap.
    stats = _FakeStatistics(win_rate=0.55, win_loss_ratio=1.5, sample_count=50)
    model = KellySizingModel(stats, min_samples=30, max_kelly_fraction=0.5)

    size = model.size(_signal(), equity=10_000.0, stop_distance=0.01)

    kelly_fraction = 0.55 - 0.45 / 1.5
    assert kelly_fraction == pytest.approx(0.25)
    assert size == pytest.approx(10_000.0 * kelly_fraction / 0.01)


def test_kelly_model_clamps_to_max_kelly_fraction() -> None:
    # f* = 0.9 - 0.1/1.0 = 0.8, far above the 0.25 cap.
    stats = _FakeStatistics(win_rate=0.9, win_loss_ratio=1.0, sample_count=50)
    model = KellySizingModel(stats, min_samples=30, max_kelly_fraction=0.25)

    size = model.size(_signal(), equity=10_000.0, stop_distance=0.01)

    assert size == pytest.approx(10_000.0 * 0.25 / 0.01)


def test_kelly_model_sizes_to_zero_below_the_minimum_sample_count() -> None:
    stats = _FakeStatistics(win_rate=0.9, win_loss_ratio=2.0, sample_count=5)
    model = KellySizingModel(stats, min_samples=30)

    assert model.size(_signal(), equity=10_000.0, stop_distance=0.01) == 0.0


def test_kelly_model_sizes_to_zero_with_no_edge() -> None:
    # f* = 0.4 - 0.6/1.0 = -0.2, negative -- no edge, size to zero.
    stats = _FakeStatistics(win_rate=0.4, win_loss_ratio=1.0, sample_count=50)
    model = KellySizingModel(stats, min_samples=30)

    assert model.size(_signal(), equity=10_000.0, stop_distance=0.01) == 0.0


def test_kelly_model_sizes_to_zero_without_a_stop_distance() -> None:
    stats = _FakeStatistics(win_rate=0.9, win_loss_ratio=2.0, sample_count=50)
    model = KellySizingModel(stats, min_samples=30)

    assert model.size(_signal(), equity=10_000.0) == 0.0


def test_kelly_model_rejects_invalid_construction_parameters() -> None:
    stats = _FakeStatistics(win_rate=0.6, win_loss_ratio=1.5, sample_count=50)
    with pytest.raises(ValueError):
        KellySizingModel(stats, min_samples=0)
    with pytest.raises(ValueError):
        KellySizingModel(stats, max_kelly_fraction=0.0)
    with pytest.raises(ValueError):
        KellySizingModel(stats, max_kelly_fraction=1.5)
