from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The output of the Strategy Validation Pipeline. A strategy passes only
    when every check passes -- there is no partial credit for a live-deployment
    gate.
    """

    strategy_name: str
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def failure_summary(self) -> str:
        failures = [check.name for check in self.checks if not check.passed]
        return ", ".join(failures) if failures else "none"


__all__ = ["CheckResult", "ValidationReport"]
