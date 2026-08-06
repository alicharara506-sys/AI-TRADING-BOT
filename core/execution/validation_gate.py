from __future__ import annotations

from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import OrderAck, OrderRequest
from core.interfaces.validation import ValidationReport


class ValidationError(Exception):
    pass


class ValidationGatedExecutionEngine:
    """Wraps any ExecutionEngine with a strategy's ValidationReport. Construction
    itself raises when the report didn't pass -- there is no code path that
    produces a working live-wired engine for an unvalidated strategy. This is
    what makes "a strategy cannot reach mode=live without a passing Validation
    Report" a structural guarantee rather than a step someone has to remember to
    run, mirroring RiskGatedExecutionEngine's construction-time enforcement.
    """

    def __init__(self, inner: ExecutionEngine, report: ValidationReport) -> None:
        if not report.passed:
            raise ValidationError(
                f"Cannot enable live execution for '{report.strategy_name}': "
                f"validation failed ({report.failure_summary()})"
            )
        self._inner = inner
        self._report = report

    @property
    def report(self) -> ValidationReport:
        return self._report

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        return await self._inner.submit_order(request)

    async def cancel_order(self, correlation_id: str) -> None:
        await self._inner.cancel_order(correlation_id)


__all__ = ["ValidationError", "ValidationGatedExecutionEngine"]
