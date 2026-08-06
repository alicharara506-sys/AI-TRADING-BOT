from __future__ import annotations

import math

from core.interfaces.reliability import ModuleReliabilityProvider
from core.interfaces.types import Direction, Evidence, Symbol, TradeSignal

_CONFIDENCE_EPSILON = 1e-6


class SignalFusion:
    """Combines independent Evidence into one TradeSignal via log-odds (logit)
    summation: each Evidence's confidence is treated as an estimated probability
    that its directional call is correct, converted to a signed log-odds
    contribution, and summed as if each source were a conditionally-independent
    likelihood update -- not a naive average, which would let many weak or
    correlated sources outvote one strong one.

    Per-module calibrated weighting, informed by a ModuleReliabilityProvider
    (HistoricalHitRateStore satisfies this structurally -- see
    core/interfaces/reliability.py), is layered on top of that same log-odds
    mechanism: every module contributes with equal (full) weight until the
    provider has enough samples for that module+symbol, exactly the "defer
    to real data once it exists" pattern EngulfingPatternModule already
    uses for its own confidence.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.6,
        reliability_provider: ModuleReliabilityProvider | None = None,
    ) -> None:
        if not 0.5 <= threshold < 1.0:
            raise ValueError("threshold must be in [0.5, 1.0)")
        self._threshold = threshold
        self._reliability_provider = reliability_provider

    def fuse(self, symbol: Symbol, evidence: list[Evidence]) -> TradeSignal | None:
        if not evidence:
            # A TradeSignal must always be backed by at least one piece of
            # Evidence -- without this guard, zero evidence produces exactly
            # 0.5 combined probability, which a threshold of exactly 0.5 (a
            # valid configuration) would not reject, yielding an evidence-free
            # "signal".
            return None

        log_odds = 0.0
        for item in evidence:
            confidence = min(max(item.confidence, _CONFIDENCE_EPSILON), 1 - _CONFIDENCE_EPSILON)
            contribution = math.log(confidence / (1 - confidence))
            contribution *= self._reliability_multiplier(item.source_module, symbol)
            if item.direction is Direction.LONG:
                log_odds += contribution
            elif item.direction is Direction.SHORT:
                log_odds -= contribution
            # Direction.NEUTRAL contributes no directional evidence.

        probability = 1.0 / (1.0 + math.exp(-log_odds))
        if probability >= 0.5:
            direction = Direction.LONG
            combined_confidence = probability
        else:
            direction = Direction.SHORT
            combined_confidence = 1.0 - probability

        if combined_confidence < self._threshold:
            return None

        return TradeSignal(
            symbol=symbol,
            direction=direction,
            combined_confidence=combined_confidence,
            threshold=self._threshold,
            evidence=tuple(evidence),
        )

    def _reliability_multiplier(self, source_module: str, symbol: Symbol) -> float:
        """1.0 (full weight, unchanged direction) with no provider or no
        history yet -- an untested module gets the same benefit of the
        doubt every module had before this weighting existed. Once enough
        samples exist, this is a linear rescale of hit_rate from [0, 1] to
        [-1, 1]: a module correct exactly half the time (no better than a
        coin flip) is fully zeroed out; one correct 100% of the time keeps
        full weight; one correct 0% of the time is exactly as informative
        as always being right, so its contribution is inverted rather than
        merely discarded.
        """
        if self._reliability_provider is None:
            return 1.0
        hit_rate = self._reliability_provider.hit_rate(source_module, symbol.canonical)
        if hit_rate is None:
            return 1.0
        return 2.0 * hit_rate - 1.0


__all__ = ["SignalFusion"]
