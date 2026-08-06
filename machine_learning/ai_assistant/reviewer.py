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
    Async because a real implementation makes a network call to an LLM
    provider; RuleBasedReviewer has no I/O of its own but still implements
    this as async to satisfy the Protocol, the same way LoggingNotifier
    does for the (also I/O-free) logging path of the Notifier Protocol.

    Nothing in this Protocol can place, modify, or cancel an order -- both
    methods return prose. AI-generated analysis reaches the trading system,
    if it does at all, only as Evidence flowing through the same
    SignalFusion -> RiskGatedExecutionEngine -> ValidationGatedExecutionEngine
    pipeline every other signal source uses; it never gets a privileged path.
    """

    async def review_validation_report(self, report: ValidationReport) -> str: ...

    async def explain_trade_signal(self, signal: TradeSignal) -> str: ...


__all__ = ["AIReviewer"]
