"""Tests for the maintenance-window evaluator.

Covers the 30-tuple grammar matrix from the design spec §9:
- Default window '0 2 * * *' is open at 02:00 local tz and closed everywhere else.
- IANA tz like 'America/Bogota' shifts the evaluation correctly.
- Wildcards '* * * * *' are always open.
- An explicit override_until in the future opens the window unconditionally.
- An expired override_until falls back to the cron check.

The class under test is window.WindowEvaluator (Tier 4 will extend it
with the global override flag; Tier 2 only handles per-tenant fields).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from migration_runner.window import WindowEvaluator


def _utc(*args: int) -> datetime:
    """Helper to build a tz-aware UTC datetime — pytest sugar."""
    return datetime(*args, tzinfo=timezone.utc)


class TestCronOnly:
    """No override; window evaluation derives entirely from cron + tz."""

    def test_default_window_open_at_02_local(self) -> None:
        # 02:00 Bogota == 07:00 UTC. Window '0 2 * * *' is open then.
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota')
        assert e.is_open(_utc(2026, 5, 23, 7, 0)) is True

    def test_default_window_closed_at_18_local(self) -> None:
        # 18:00 Bogota == 23:00 UTC. Window '0 2 * * *' is closed.
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota')
        assert e.is_open(_utc(2026, 5, 23, 23, 0)) is False

    def test_wildcard_window_always_open(self) -> None:
        e = WindowEvaluator(cron='* * * * *', tz='UTC')
        assert e.is_open(_utc(2026, 5, 23, 14, 17)) is True

    def test_weekdays_only_window(self) -> None:
        # '0 2 * * 1-5' — weekdays only.  Sat = day 6 -> closed.
        # 2026-05-23 is a Saturday in the Gregorian calendar.
        e = WindowEvaluator(cron='0 2 * * 1-5', tz='UTC')
        assert e.is_open(_utc(2026, 5, 23, 2, 0)) is False
        # Move to Monday 2026-05-25.
        assert e.is_open(_utc(2026, 5, 25, 2, 0)) is True

    def test_invalid_cron_raises(self) -> None:
        with pytest.raises(ValueError, match='invalid cron'):
            WindowEvaluator(cron='not a cron', tz='UTC')


class TestOverride:
    """maintenance_window_override_until — Tier 4 surface; runner honours
    it as the very first check."""

    def test_future_override_opens_window(self) -> None:
        # Cron would be closed (18:00 Bogota) but override_until is in
        # the future -> open regardless.
        e = WindowEvaluator(
            cron='0 2 * * *',
            tz='America/Bogota',
            override_until=_utc(2026, 5, 24, 0, 0),
        )
        assert e.is_open(_utc(2026, 5, 23, 23, 0)) is True

    def test_expired_override_falls_back_to_cron(self) -> None:
        # override_until in the past -> ignore it, check cron.
        e = WindowEvaluator(
            cron='0 2 * * *',
            tz='America/Bogota',
            override_until=_utc(2026, 5, 22, 0, 0),
        )
        assert e.is_open(_utc(2026, 5, 23, 23, 0)) is False
        assert e.is_open(_utc(2026, 5, 23, 7, 0)) is True

    def test_global_override_flag_opens_window(self) -> None:
        # Tier 4's global override flag (feature flag in control plane).
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota', global_override=True)
        assert e.is_open(_utc(2026, 5, 23, 23, 0)) is True


class TestNextOpen:
    """next_open() — drives `tenant_migration_jobs.blocked_until` in
    the proper hot-loop fix."""

    def test_returns_now_when_already_open(self) -> None:
        # 02:30 Bogota = 07:30 UTC, cron='0 2 * * *' fires at 02:00
        # Bogota = 07:00 UTC — we're inside the 1h tolerance.
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota')
        now = _utc(2026, 5, 23, 7, 30)
        assert e.is_open(now) is True
        assert e.next_open(now) == now

    def test_returns_next_cron_firing_when_closed(self) -> None:
        # 18:00 Bogota = 23:00 UTC. Next firing is 02:00 Bogota on
        # 2026-05-24 = 07:00 UTC.
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota')
        now = _utc(2026, 5, 23, 23, 0)
        assert e.is_open(now) is False
        assert e.next_open(now) == _utc(2026, 5, 24, 7, 0)

    def test_falls_through_to_cron_when_override_past(self) -> None:
        # Expired override; next_open uses cron only.
        e = WindowEvaluator(
            cron='0 2 * * *',
            tz='America/Bogota',
            override_until=_utc(2026, 5, 22, 0, 0),
        )
        now = _utc(2026, 5, 23, 23, 0)
        assert e.next_open(now) == _utc(2026, 5, 24, 7, 0)

    def test_global_override_returns_now(self) -> None:
        # global_override = is_open is always True, so next_open is now.
        e = WindowEvaluator(cron='0 2 * * *', tz='America/Bogota', global_override=True)
        now = _utc(2026, 5, 23, 23, 0)
        assert e.next_open(now) == now
