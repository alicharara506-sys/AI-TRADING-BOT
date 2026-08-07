from __future__ import annotations


class HistoricalHitRateStore:
    """Tracks per-(module, symbol) win/loss outcomes and exposes an empirical
    hit rate. This is the "Analytics Engine's historical hit-rate store" that
    pattern-recognition modules (candlesticks, harmonics, chart patterns) were
    explicitly designed to defer to once it existed: confidence for a pattern
    instance should come from real backtested performance for that
    pattern/symbol, not a static geometric heuristic alone.
    """

    def __init__(self, *, min_samples: int = 5) -> None:
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        self._min_samples = min_samples
        self._wins: dict[tuple[str, str], int] = {}
        self._totals: dict[tuple[str, str], int] = {}

    def record_outcome(self, module_name: str, symbol: str, *, won: bool) -> None:
        key = (module_name, symbol)
        self._totals[key] = self._totals.get(key, 0) + 1
        if won:
            self._wins[key] = self._wins.get(key, 0) + 1

    def hit_rate(self, module_name: str, symbol: str) -> float | None:
        """The empirical win rate, or None if there isn't yet enough history
        (fewer than min_samples outcomes) to trust it over a geometric
        fallback."""
        key = (module_name, symbol)
        total = self._totals.get(key, 0)
        if total < self._min_samples:
            return None
        wins = self._wins.get(key, 0)
        return wins / total

    def sample_count(self, module_name: str, symbol: str) -> int:
        return self._totals.get((module_name, symbol), 0)

    def tracked_keys(self) -> list[tuple[str, str]]:
        """Every (module_name, symbol) pair with at least one recorded
        outcome -- lets a caller (reporting.agent_accuracy_report) build a
        report across everything the store has ever seen, without already
        having to know every module/symbol combination in advance.
        """
        return list(self._totals.keys())


__all__ = ["HistoricalHitRateStore"]
