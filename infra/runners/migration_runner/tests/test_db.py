"""Unit tests for the JobStore SQL surface.

Drives a fake psycopg-shaped cursor to assert SQL shapes + bound
parameters. Integration against real Postgres lives in Tier 0's
verification + the agentlab smoke (see plan §4 Tier 2 acceptance).
"""

from __future__ import annotations

from dataclasses import dataclass

from migration_runner.db import JobStore


@dataclass
class FakeCursor:
    """Minimal psycopg-cursor stand-in. Captures executed SQL +
    params; returns scripted rows from fetchone()."""

    fetch_queue: list = None  # type: ignore[assignment]
    executed: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.fetch_queue = list(self.fetch_queue or [])
        self.executed = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((' '.join(sql.split()), params))

    def fetchone(self):
        return self.fetch_queue.pop(0) if self.fetch_queue else None


class FakeConn:
    def __init__(self, cur: FakeCursor) -> None:
        self._cur = cur
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):  # context manager protocol
        cur = self._cur

        class _CM:
            def __enter__(_self):  # noqa: N805
                return cur

            def __exit__(_self, *a):  # noqa: N805, ARG002
                return None

        return _CM()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _make_store(fetch_rows: list) -> tuple[JobStore, FakeCursor, FakeConn]:
    cur = FakeCursor(fetch_queue=fetch_rows)
    conn = FakeConn(cur)
    store = JobStore(dsn='postgres://test', conn_factory=lambda _dsn: conn)
    return store, cur, conn


class TestClaimNextJob:
    def test_returns_job_row_when_one_queued(self) -> None:
        # claim_next_job runs two SQL statements: SELECT then UPDATE.
        # fetchone() returns the SELECT's row.
        store, cur, _ = _make_store(
            fetch_rows=[
                (
                    'job-uuid',
                    'tenant-uuid',
                    'acme',
                    'acme',  # db_name
                    'sha-abc',
                    30,  # timeout_minutes
                    0,  # retry_count
                    '0 2 * * *',
                    'America/Bogota',
                    None,
                    'canary',
                    None,  # maintenance_window_override_until (Tier 4)
                    False,  # migration_dry_run (Tier 7)
                )
            ]
        )
        with store.cursor() as c:
            job = store.claim_next_job(c)
        assert job is not None
        assert job.id == 'job-uuid'
        assert job.tenant_slug == 'acme'
        assert job.maintenance_window == '0 2 * * *'
        # Two SQL statements executed (SELECT then UPDATE).
        assert len(cur.executed) == 2
        select_sql = cur.executed[0][0]
        assert 'FOR UPDATE OF j SKIP LOCKED' in select_sql
        assert "status IN ('queued','blocked')" in select_sql
        assert "wave, 'canary') != 'paused'" in select_sql
        update_sql = cur.executed[1][0]
        assert "SET status = 'running'" in update_sql
        # Two params now: runner_host + job_id (Tier 7 forensics).
        assert cur.executed[1][1] == ('unknown', 'job-uuid')

    def test_returns_none_when_queue_empty(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[])
        with store.cursor() as c:
            assert store.claim_next_job(c) is None
        # Only one SQL was executed (the SELECT). The UPDATE is skipped.
        assert len(cur.executed) == 1


class TestFinalizeDone:
    def test_writes_job_row_and_tenant_sha_in_same_tx(self) -> None:
        store, cur, conn = _make_store(fetch_rows=[])
        with store.cursor() as c:
            store.finalize_done(c, 'job-1', 'tenant-1', 'sha-new')
        # Two UPDATEs.
        assert len(cur.executed) == 2
        assert "status = 'done'" in cur.executed[0][0]
        assert 'last_migrated_sha' in cur.executed[1][0]
        # One commit on context exit.
        assert conn.commits == 1


class TestFinalizeFailed:
    def test_pauses_tenant(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[])
        with store.cursor() as c:
            store.finalize_failed(
                c,
                'job-1',
                'tenant-1',
                status='failed',
                error_excerpt='boom',
            )
        # Two UPDATEs: job row + tenants.wave -> paused.
        assert len(cur.executed) == 2
        assert "wave = 'paused'" in cur.executed[1][0]


class TestRetryTransient:
    def test_bumps_retry_count_and_pushes_enqueued_at_forward(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[])
        with store.cursor() as c:
            store.retry_transient(
                c, 'job-1', backoff_seconds=300, error_excerpt='conn refused'
            )
        sql, params = cur.executed[0]
        assert 'retry_count = retry_count + 1' in sql
        assert "status = 'queued'" in sql
        assert params == ('conn refused', 300, 'job-1')


class TestHeartbeat:
    def test_returns_current_status(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[('running',)])
        with store.cursor() as c:
            assert store.record_heartbeat(c, 'job-1') == 'running'
        assert 'heartbeat_at = now()' in cur.executed[0][0]

    def test_detects_cancellation(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[('cancelled',)])
        with store.cursor() as c:
            assert store.record_heartbeat(c, 'job-1') == 'cancelled'


class TestTransitionToBlocked:
    """Proper hot-loop fix: claim_next_job filters blocked rows by
    `blocked_until <= now()`; transition_to_blocked writes that column."""

    def test_writes_blocked_until_when_provided(self) -> None:
        from datetime import datetime, timezone

        store, cur, _ = _make_store(fetch_rows=[])
        next_open = datetime(2026, 5, 24, 7, 0, tzinfo=timezone.utc)
        with store.cursor() as c:
            store.transition_to_blocked(c, 'job-1', next_open)
        sql, params = cur.executed[0]
        assert "status = 'blocked'" in sql
        assert 'blocked_until = %s' in sql
        # Bound params: (blocked_until, job_id) in that order.
        assert params == (next_open, 'job-1')

    def test_writes_null_when_omitted(self) -> None:
        # Back-compat: callers that don't compute next-open get NULL,
        # which the claim filter treats as "recheck on next poll".
        store, cur, _ = _make_store(fetch_rows=[])
        with store.cursor() as c:
            store.transition_to_blocked(c, 'job-1')
        _sql, params = cur.executed[0]
        assert params == (None, 'job-1')


class TestClaimNextJob:
    """Verify the SQL filter shape — does NOT execute against Postgres,
    just asserts the predicate that PR #94's hot-loop fix needs."""

    def test_filter_includes_queued_and_blocked_with_elapsed_until(self) -> None:
        store, cur, _ = _make_store(fetch_rows=[])  # empty fetch -> None
        with store.cursor() as c:
            assert store.claim_next_job(c) is None
        sql = cur.executed[0][0]
        # The new predicate must include both branches:
        assert "j.status = 'queued'" in sql
        assert "j.status = 'blocked'" in sql
        # Blocked rows are gated by blocked_until comparison.
        assert 'blocked_until' in sql
        # Back-compat: NULL means "recheck on next poll".
        assert 'COALESCE(j.blocked_until,' in sql
