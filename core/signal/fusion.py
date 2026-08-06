from __future__ import annotations

import math

from core.interfaces.types import Direction, Evidence, Symbol, TradeSignal

_CONFIDENCE_EPSILON = 1e-6


class SignalFusion:
    """Combines independent Evidence into one TradeSignal via log-odds (logit)
    summation: each Evidence's confidence is treated as an estimated probability
    that its directional call is correct, converted to a signed log-odds
    contribution, and summed as if each source were a conditionally-independent
    likelihood update -- not a naive average, which would let many weak or
    correlated sources outvote one strong one.

    Per-module calibrated weighting (informed by the Analytics Engine's
    historical hit-rate store) is a later addition on top of this same
    mechanism; every module contributes with equal weight until that engine
    exists to supply real calibration data.
    """

    def __init__(self, *, threshold: float = 0.6) -> None:
        if not 0.5 <= threshold < 1.0:
            raise ValueError("threshold must be in [0.5, 1.0)")
        self._threshold = threshold

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


__all__ = ["SignalFusion"]
