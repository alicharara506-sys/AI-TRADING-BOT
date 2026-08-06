from __future__ import annotations

from dataclasses import dataclass

from core.interfaces.analysis import AnalysisModule
from core.interfaces.types import Evidence, MarketContext, Symbol, TradeSignal
from core.signal.fusion import SignalFusion


@dataclass(frozen=True, slots=True)
class SignalRecord:
    """The persisted, queryable result of one SignalEngine.evaluate() call --
    the complete Evidence trail plus the fusion outcome, whether or not it
    cleared the threshold. This *is* the explainability contract: nothing else
    needs to be built to "explain" a signal, because the record already carries
    every module's contribution.
    """

    symbol: Symbol
    evidence: tuple[Evidence, ...]
    signal: TradeSignal | None

    def explain(self) -> str:
        lines = [f"Symbol: {self.symbol.canonical}"]
        if not self.evidence:
            lines.append("No evidence collected.")
        for item in self.evidence:
            lines.append(
                f"  - [{item.source_module}] {item.direction.value} "
                f"(confidence={item.confidence:.2f}) {item.rationale}"
            )
        if self.signal is None:
            lines.append("Result: no signal (below threshold or no evidence).")
        else:
            lines.append(
                f"Result: {self.signal.direction.value.upper()} "
                f"(combined_confidence={self.signal.combined_confidence:.2f}, "
                f"threshold={self.signal.threshold:.2f})"
            )
        return "\n".join(lines)


class SignalEngine:
    """Runs every registered AnalysisModule over a MarketContext, fuses their
    Evidence into a TradeSignal, and persists a human-readable, queryable
    SignalRecord of the whole evaluation -- including evaluations that didn't
    clear the fusion threshold, since a below-threshold result is still useful
    for research/ML training and for auditing why a bar produced no trade.
    """

    def __init__(self, fusion: SignalFusion) -> None:
        self._fusion = fusion
        self._modules: list[AnalysisModule] = []
        self._history: list[SignalRecord] = []

    def register_module(self, module: AnalysisModule) -> None:
        self._modules.append(module)

    def evaluate(self, context: MarketContext) -> TradeSignal | None:
        evidence: list[Evidence] = []
        for module in self._modules:
            evidence.extend(module.analyze(context))

        signal = self._fusion.fuse(context.symbol, evidence)
        self._history.append(
            SignalRecord(symbol=context.symbol, evidence=tuple(evidence), signal=signal)
        )
        return signal

    def history(self) -> list[SignalRecord]:
        return list(self._history)


__all__ = ["SignalEngine", "SignalRecord"]
