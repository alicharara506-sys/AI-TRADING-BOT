from __future__ import annotations

from dataclasses import dataclass

from analytics.hit_rate_store import HistoricalHitRateStore


@dataclass(frozen=True, slots=True)
class ModuleAccuracy:
    """One (module, symbol) pair's empirical track record, straight from
    HistoricalHitRateStore -- hit_rate is None when there aren't yet enough
    recorded outcomes to trust it, same as the store's own contract.
    """

    module_name: str
    symbol: str
    hit_rate: float | None
    sample_count: int


@dataclass(frozen=True, slots=True)
class AgentAccuracyReport:
    """The "per-module agent accuracy" report: every (module, symbol) pair
    HistoricalHitRateStore has ever recorded an outcome for, rendered as a
    single report. The store already tracked this raw data (win_rate/
    sample_count per key) -- this class only adds enumeration
    (tracked_keys) and a rendered view over it, not a second source of
    truth.
    """

    modules: tuple[ModuleAccuracy, ...]

    @classmethod
    def from_store(cls, store: HistoricalHitRateStore) -> AgentAccuracyReport:
        modules = tuple(
            sorted(
                (
                    ModuleAccuracy(
                        module_name=module_name,
                        symbol=symbol,
                        hit_rate=store.hit_rate(module_name, symbol),
                        sample_count=store.sample_count(module_name, symbol),
                    )
                    for module_name, symbol in store.tracked_keys()
                ),
                key=lambda entry: (entry.module_name, entry.symbol),
            )
        )
        return cls(modules=modules)

    def render(self) -> str:
        if not self.modules:
            return "Agent accuracy report: no outcomes recorded yet."
        lines = ["Agent accuracy report:"]
        for entry in self.modules:
            hit_rate_text = (
                f"{entry.hit_rate * 100:.1f}%" if entry.hit_rate is not None else "not enough data"
            )
            lines.append(
                f"  - [{entry.module_name}] {entry.symbol}: {hit_rate_text} "
                f"({entry.sample_count} samples)"
            )
        return "\n".join(lines)


__all__ = ["AgentAccuracyReport", "ModuleAccuracy"]
