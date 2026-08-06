from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import TradeSignal
from core.interfaces.validation import ValidationReport


@runtime_checkable
class AIReviewer(Protocol):
    """Reviews Validation Reports and explains TradeSignals in natural
    language, backed by the same numeric evidence those components already
    produced -- never an independent, opaque judgment. Interface-isolated so
    a real LLM-backed implementation is a swap-in later without touching any
    caller of this Protocol, per the architecture's explicit requirement.
    """

    def review_validation_report(self, report: ValidationReport) -> str: ...

    def explain_trade_signal(self, signal: TradeSignal) -> str: ...


__all__ = ["AIReviewer"]
