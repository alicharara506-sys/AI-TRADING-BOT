from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from core.interfaces.validation import CheckResult


class LookAheadBiasCheck:
    """Mechanically verifies a sequence of bar timestamps is strictly
    non-decreasing. A backtest that ever processed a bar out of chronological
    order could have let a strategy or indicator see future data -- exactly the
    look-ahead bias this check exists to catch, as an automated assertion over
    the backtest's own data pipeline rather than a manual review checklist.
    """

    name = "look_ahead_bias"

    def run(self, bar_timestamps: Sequence[datetime]) -> CheckResult:
        for index in range(1, len(bar_timestamps)):
            previous, current = bar_timestamps[index - 1], bar_timestamps[index]
            if current < previous:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    detail={
                        "reason": "bars processed out of chronological order",
                        "index": index,
                        "previous": previous.isoformat(),
                        "current": current.isoformat(),
                    },
                )

        return CheckResult(
            name=self.name, passed=True, detail={"bars_checked": len(bar_timestamps)}
        )


__all__ = ["LookAheadBiasCheck"]
