from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from connectors.mt_common.reconnect import HeartbeatMonitor, ReconnectPolicy
from core.interfaces.types import ConnectionState
from core.kernel.clock import TestClock


def test_delay_grows_exponentially_and_caps() -> None:
    policy = ReconnectPolicy(initial_delay=1.0, max_delay=10.0, multiplier=2.0)

    assert policy.delay_for_attempt(1) == pytest.approx(1.0)
    assert policy.delay_for_attempt(2) == pytest.approx(2.0)
    assert policy.delay_for_attempt(3) == pytest.approx(4.0)
    assert policy.delay_for_attempt(5) == pytest.approx(10.0)


def test_delay_rejects_invalid_attempt() -> None:
    policy = ReconnectPolicy()
    with pytest.raises(ValueError):
        policy.delay_for_attempt(0)


def test_invalid_policy_parameters_rejected() -> None:
    with pytest.raises(ValueError):
        ReconnectPolicy(multiplier=1.0)


def test_heartbeat_starts_disconnected() -> None:
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    monitor = HeartbeatMonitor(
        clock, degraded_after=timedelta(seconds=5), lost_after=timedelta(seconds=10)
    )

    assert monitor.state() == ConnectionState.DISCONNECTED


def test_heartbeat_transitions_connected_degraded_lost() -> None:
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    monitor = HeartbeatMonitor(
        clock, degraded_after=timedelta(seconds=5), lost_after=timedelta(seconds=10)
    )

    monitor.record_heartbeat()
    assert monitor.state() == ConnectionState.CONNECTED

    clock.advance(timedelta(seconds=6))
    assert monitor.state() == ConnectionState.DEGRADED

    clock.advance(timedelta(seconds=5))
    assert monitor.state() == ConnectionState.LOST


def test_lost_after_must_exceed_degraded_after() -> None:
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        HeartbeatMonitor(
            clock, degraded_after=timedelta(seconds=10), lost_after=timedelta(seconds=5)
        )
