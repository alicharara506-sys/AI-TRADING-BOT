from __future__ import annotations

import pytest

from core.indicators.builtins import register_builtin_indicators
from core.indicators.registry import IndicatorRegistry, IndicatorRegistryError
from core.indicators.trend import SimpleMovingAverage


def test_register_and_create() -> None:
    registry = IndicatorRegistry()
    registry.register("sma_5", lambda: SimpleMovingAverage(period=5))

    indicator = registry.create("sma_5")

    assert isinstance(indicator, SimpleMovingAverage)


def test_duplicate_registration_raises() -> None:
    registry = IndicatorRegistry()
    registry.register("sma_5", lambda: SimpleMovingAverage(period=5))

    with pytest.raises(IndicatorRegistryError):
        registry.register("sma_5", lambda: SimpleMovingAverage(period=5))


def test_create_unregistered_raises() -> None:
    registry = IndicatorRegistry()

    with pytest.raises(IndicatorRegistryError):
        registry.create("does_not_exist")


def test_register_builtin_indicators_populates_expected_names() -> None:
    registry = IndicatorRegistry()
    register_builtin_indicators(registry)

    assert registry.names() == ["ema_12", "ema_26", "rsi_14", "sma_20", "sma_50"]
