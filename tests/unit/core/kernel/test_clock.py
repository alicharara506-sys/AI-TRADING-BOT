from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.kernel.clock import LiveClock, TestClock


def test_live_clock_returns_utc_now() -> None:
    clock = LiveClock()
    before = datetime.now(UTC)
    now = clock.now()
    after = datetime.now(UTC)

    assert before <= now <= after


def test_test_clock_is_deterministic_until_advanced() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = TestClock(start)

    assert clock.now() == start
    clock.advance(timedelta(hours=1))
    assert clock.now() == start + timedelta(hours=1)


def test_test_clock_set_jumps_directly() -> None:
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    target = datetime(2026, 6, 1, tzinfo=UTC)

    clock.set(target)

    assert clock.now() == target
