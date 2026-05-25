"""Postgres helpers for the migration-job queue.

Wraps the control-plane Postgres connection and exposes the four
critical operations the runner uses:

- claim_next_job(): SELECT ... FOR UPDATE SKIP LOCKED + UPDATE to flip
  status to 'running'. Single-claim invariant: two runners cannot
  return the same row.
- transition_to_blocked(): outside-window observation; back-to-queued
  with no retry_count bump.
- finalize_done(): single-tx UPDATE of the job row + tenants.last_migrated_sha.
- finalize_failed/timedout(): UPDATE the job row, set tenants.wave='paused'.
- record_heartbeat(): UPDATE heartbeat_at + return current status so the
  heartbeat thread can detect operator cancellation.

Connection pool: a single shared psycopg connection-pool, lazily
initialised on first call. The runner's main loop is single-threaded
per process, but the heartbeat thread also reads/writes — pool is the
simplest way to keep those isolated.

This module is intentionally thin — the hard logic (window check,
snapshot, subprocess) lives in runner.py. db.py is the SQL surface.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JobRow:
    """In-memory snapshot of a `tenant_migration_jobs` row + joined
    tenant data the runner needs to make decisions."""

    id: str  # uuid
    tenant_id: str
    tenant_slug: str
    tenant_db_name: str
    target_sha: str
    timeout_minutes: int
    retry_count: int
    maintenance_window: str
    tz: str
    last_migrated_sha: Optional[str]
    wave: Optional[str]
    # Tier 4 — per-tenant override surface. When set + in the future,
    # the runner treats the window as open regardless of cron.
    maintenance_window_override_until: Optional[datetime] = None
    # Tier 7 — when true, runner clones the tenant DB before migrating.
    migration_dry_run: bool = False


class JobStore:
    """Postgres-backed queue store. One per runner process.

    Connection is lazy + reconnect-on-failure (psycopg's default
    pool semantics). The caller (runner.py) wraps each iteration of
    the main loop in a `with store.cursor() as cur:` block.
    """

    def __init__(
        self,
        dsn: str,
        *,
        conn_factory: Any = None,
        runner_host: Optional[str] = None,
    ) -> None:
        """Args:
        dsn: Postgres connection string (CONTROL_PLANE_PG_DSN).
        conn_factory: Override for psycopg.connect — tests inject a
            fake connection here. Production passes None.
        runner_host: Tier 7 forensics. Stamped onto the claimed row.
        """
        self._dsn = dsn
        self._conn_factory = conn_factory
        self._conn: Any = None
        self._runner_host = runner_host or 'unknown'

    def _connect(self) -> Any:
        if self._conn is None or getattr(self._conn, 'closed', False):
            if self._conn_factory is not None:
                self._conn = self._conn_factory(self._dsn)
            else:  # pragma: no cover — only exercised in container
                import psycopg

                self._conn = psycopg.connect(self._dsn, autocommit=False)
        return self._conn

    @contextmanager
    def cursor(self) -> Iterator[Any]:
        """Yield a cursor inside a transaction. Caller commits on
        success; any exception triggers rollback."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ── Queue ops ────────────────────────────────────────────────────

    def claim_next_job(self, cur: Any) -> Optional[JobRow]:
        """Atomic claim of the oldest eligible queued/blocked row.

        A 'blocked' row is eligible only when its `blocked_until` has
        elapsed (or is NULL — back-compat for rows touched only by the
        MVP sleep-on-blocked patch from PR #94). The partial index
        `tenant_migration_jobs_blocked_until_idx` keeps the predicate
        cheap.

        Single transaction:
          SELECT ... FOR UPDATE SKIP LOCKED;
          UPDATE ... SET status='running', started_at=now(),
                        heartbeat_at=now()
            WHERE id = <claimed_id>;
        """
        cur.execute(
            """
            SELECT j.id, j.tenant_id, t.slug, t.db_name, j.target_sha,
                   j.timeout_minutes, j.retry_count,
                   t.maintenance_window, t.tz, t.last_migrated_sha, t.wave,
                   t.maintenance_window_override_until,
                   COALESCE(j.migration_dry_run, false)
            FROM tenant_migration_jobs j
            JOIN tenants t ON t.id = j.tenant_id
            WHERE (
                    j.status = 'queued'
                 OR (j.status = 'blocked'
                     AND COALESCE(j.blocked_until, '-infinity'::timestamptz) <= now())
                  )
              AND COALESCE(t.wave, 'canary') != 'paused'
              AND j.enqueued_at <= now()
            ORDER BY j.enqueued_at ASC, j.id ASC
            FOR UPDATE OF j SKIP LOCKED
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = 'running',
                started_at = now(),
                heartbeat_at = now(),
                runner_host = %s
            WHERE id = %s
            """,
            (self._runner_host, row[0]),
        )
        return JobRow(
            id=str(row[0]),
            tenant_id=str(row[1]),
            tenant_slug=row[2],
            tenant_db_name=row[3],
            target_sha=row[4],
            timeout_minutes=row[5],
            retry_count=row[6],
            maintenance_window=row[7],
            tz=row[8],
            last_migrated_sha=row[9],
            wave=row[10],
            maintenance_window_override_until=row[11],
            migration_dry_run=bool(row[12]),
        )

    def transition_to_blocked(
        self, cur: Any, job_id: str, blocked_until: Optional[datetime] = None
    ) -> None:
        """Outside-window observation — clear started_at/heartbeat and
        return the row to the queue with `status='blocked'`. No
        retry_count bump.

        `blocked_until` is the next eligible firing time computed by
        the runner from the tenant's window. claim_next_job filters
        blocked rows by this column so the daemon won't re-claim until
        it has elapsed. NULL means "recheck on next poll" (back-compat
        for callers that haven't been updated to the new contract)."""
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = 'blocked',
                started_at = NULL,
                heartbeat_at = NULL,
                finished_at = NULL,
                blocked_until = %s
            WHERE id = %s
            """,
            (blocked_until, job_id),
        )

    def transition_to_skipped(self, cur: Any, job_id: str) -> None:
        """Idempotency hit — tenant already at target_sha. Mark
        skipped, do not run Odoo."""
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = 'skipped',
                finished_at = now()
            WHERE id = %s
            """,
            (job_id,),
        )

    def finalize_done(
        self, cur: Any, job_id: str, tenant_id: str, target_sha: str
    ) -> None:
        """Single-tx flip: job -> done AND tenants.last_migrated_sha
        bumped. Risk #2 mitigation: either both apply or neither."""
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = 'done',
                finished_at = now(),
                heartbeat_at = NULL
            WHERE id = %s
            """,
            (job_id,),
        )
        cur.execute(
            """
            UPDATE tenants
            SET last_migrated_sha = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (target_sha, tenant_id),
        )

    def finalize_failed(
        self,
        cur: Any,
        job_id: str,
        tenant_id: str,
        *,
        status: str,
        error_excerpt: str,
    ) -> None:
        """Terminal failure — mark `failed` or `timedout`, auto-pause
        the tenant (Tier 4 operator un-pauses)."""
        assert status in ('failed', 'timedout')
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = %s,
                finished_at = now(),
                heartbeat_at = NULL,
                error_excerpt = %s
            WHERE id = %s
            """,
            (status, error_excerpt, job_id),
        )
        cur.execute(
            """
            UPDATE tenants
            SET wave = 'paused',
                updated_at = now()
            WHERE id = %s
            """,
            (tenant_id,),
        )

    def retry_transient(
        self,
        cur: Any,
        job_id: str,
        *,
        backoff_seconds: int,
        error_excerpt: str,
    ) -> None:
        """Tier 3 transient-failure handler — return the row to queue
        with retry_count bumped and enqueued_at pushed forward."""
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET status = 'queued',
                started_at = NULL,
                finished_at = NULL,
                heartbeat_at = NULL,
                retry_count = retry_count + 1,
                error_excerpt = %s,
                enqueued_at = now() + (%s::int * interval '1 second')
            WHERE id = %s
            """,
            (error_excerpt, backoff_seconds, job_id),
        )

    # ── Heartbeat + cancellation ─────────────────────────────────────

    def record_heartbeat(self, cur: Any, job_id: str) -> Optional[str]:
        """Update heartbeat_at and return the CURRENT status. The
        heartbeat thread checks the return value: if status flipped to
        'cancelled' by Tier 1, abort the subprocess."""
        cur.execute(
            """
            UPDATE tenant_migration_jobs
            SET heartbeat_at = now()
            WHERE id = %s
            RETURNING status
            """,
            (job_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def write_snapshot_id(self, cur: Any, job_id: str, snapshot_id: str) -> None:
        cur.execute(
            'UPDATE tenant_migration_jobs SET snapshot_id = %s WHERE id = %s',
            (snapshot_id, job_id),
        )


def utcnow() -> datetime:
    """Centralised UTC clock — easy to monkeypatch in tests."""
    return datetime.now(tz=timezone.utc)
