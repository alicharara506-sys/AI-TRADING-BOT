from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CommissionModel(Protocol):
    def calculate(self, *, volume: float, price: float) -> float: ...


class ZeroCommission:
    """The explicit default: no commission cost modeled. A real, valid choice
    in its own right (ECN-style zero-commission accounts exist), not a
    placeholder standing in for a "real" model."""

    def calculate(self, *, volume: float, price: float) -> float:
        return 0.0


class PerLotCommission:
    """A fixed cost per traded lot, independent of price -- the most common
    commission structure MT4/MT5 brokers actually quote."""

    def __init__(self, rate_per_lot: float) -> None:
        if rate_per_lot < 0:
            raise ValueError("rate_per_lot must be >= 0")
        self._rate_per_lot = rate_per_lot

    def calculate(self, *, volume: float, price: float) -> float:
        return volume * self._rate_per_lot


__all__ = ["CommissionModel", "PerLotCommission", "ZeroCommission"]
