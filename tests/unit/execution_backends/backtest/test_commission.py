from __future__ import annotations

import pytest

from execution_backends.backtest.commission import PerLotCommission, ZeroCommission


def test_zero_commission_is_always_zero() -> None:
    model = ZeroCommission()

    assert model.calculate(volume=1.0, price=1.1) == 0.0
    assert model.calculate(volume=100.0, price=50_000.0) == 0.0


def test_per_lot_commission_scales_with_volume_only() -> None:
    model = PerLotCommission(rate_per_lot=7.0)

    assert model.calculate(volume=1.0, price=1.1) == pytest.approx(7.0)
    assert model.calculate(volume=2.5, price=999.0) == pytest.approx(17.5)


def test_per_lot_commission_rejects_negative_rate() -> None:
    with pytest.raises(ValueError):
        PerLotCommission(rate_per_lot=-1.0)
