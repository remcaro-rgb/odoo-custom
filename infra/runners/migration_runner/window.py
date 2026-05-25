"""Maintenance-window evaluator.

Each tenant has a `maintenance_window` cron string and a `tz` IANA
identifier. The runner consults the WindowEvaluator before promoting a
job from `queued` to `running`:

- If the (override OR global override) escape hatch is set, the window
  is treated as open and the job runs immediately.
- Otherwise the cron expression is evaluated against the tenant's local
  time. A window is "open" if the cron would fire WITHIN A 1-HOUR
  TOLERANCE WINDOW of the current local time — we don't expect to hit
  the exact second the cron schedules, only the surrounding hour.

The 1-hour tolerance matches the spec §9 grammar ("daily at 02:00"
means "anywhere between 02:00 and 02:59"), keeps `0 2 * * *` cleanly
readable, and avoids race conditions where the runner polls a few
seconds past 02:00:00 and misses the open window for 24 hours.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, croniter


@dataclass(frozen=True, slots=True)
class WindowEvaluator:
    """Per-tenant window state.

    Args:
        cron: 5-field cron expression. Default '0 2 * * *' means "open
            at 02:00 every day".
        tz: IANA timezone (e.g. 'America/Bogota'). Cron fields are
            interpreted in this timezone.
        override_until: when set and in the future at the call site,
            forces is_open() to return True regardless of cron.
        global_override: Tier 4 emergency switch. Same effect as
            override_until but cluster-wide.
    """

    cron: str
    tz: str
    override_until: Optional[datetime] = None
    global_override: bool = False

    # 1-hour tolerance — see module docstring.
    TOLERANCE: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        # Fail fast on bad cron syntax — the runner shouldn't park a
        # job in 'blocked' forever because of a typo upstream.
        if not croniter.is_valid(self.cron):
            raise ValueError(f'invalid cron expression: {self.cron!r}')
        # Validate tz too — ZoneInfo lookups are lazy otherwise.
        try:
            ZoneInfo(self.tz)
        except Exception as exc:  # ZoneInfoNotFoundError on Python 3.12
            raise ValueError(f'invalid IANA tz: {self.tz!r}') from exc

    def is_open(self, now: datetime) -> bool:
        """Return True if the migration may run at `now` (UTC).

        Evaluation order:
        1. Global override -> always open.
        2. Override-until in the future -> open.
        3. Cron expression evaluated in the tenant's tz with the
           1-hour tolerance -> open if the most-recent past firing is
           within TOLERANCE of `now`.
        """
        if self.global_override:
            return True
        if self.override_until is not None and self.override_until > now:
            return True

        # Convert `now` (UTC) to the tenant's tz so the cron fields are
        # evaluated against the tenant's local clock.
        local_now = now.astimezone(ZoneInfo(self.tz))
        # croniter.get_prev returns the most-recent firing STRICTLY
        # before its start time, so at the exact firing minute (e.g.
        # 02:00:00) it jumps a full day. Probe 1s into the future so
        # the firing AT local_now is included in the search, without
        # picking up the upcoming-minute firing for `* * * * *`.
        probe = local_now + timedelta(seconds=1)
        try:
            it = croniter(self.cron, probe)
        except CroniterBadCronError as exc:  # defense in depth
            raise ValueError(f'invalid cron expression: {self.cron!r}') from exc
        prev_firing_local = it.get_prev(datetime)
        # prev_firing_local is tz-aware (matches local_now).
        delta = local_now - prev_firing_local
        return delta >= timedelta(0) and delta <= self.TOLERANCE

    def next_open(self, now: datetime) -> datetime:
        """Return the next UTC datetime when is_open(now) would become
        True.

        Used by the runner to set `tenant_migration_jobs.blocked_until`
        when transitioning a job to 'blocked'. The daemon's
        claim_next_job filters
            (status='blocked' AND blocked_until <= now())
        so a blocked job stays invisible to the daemon until the
        returned time has elapsed.

        Returned time is:
        - now() if the global override is set (open now).
        - override_until if that's in the future and earlier than the
          next cron firing.
        - next cron firing in the tenant's tz (converted back to UTC).

        Caller is responsible for storing this as UTC.
        """
        # If we'd already be open, the "next open" is right now — the
        # caller can choose to short-circuit and not park the job.
        if self.is_open(now):
            return now
        candidates: list[datetime] = []
        if self.override_until is not None and self.override_until > now:
            candidates.append(self.override_until)
        # Next cron firing in the tenant's tz, converted to UTC.
        local_now = now.astimezone(ZoneInfo(self.tz))
        it = croniter(self.cron, local_now)
        next_firing_local = it.get_next(datetime)
        candidates.append(next_firing_local.astimezone(timezone.utc))
        # Earliest opener wins.
        return min(candidates)
