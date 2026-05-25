"""End-to-end Runner.run_once() coverage with the subprocess stubbed.

Drives Runner through the four critical happy + sad paths:
- idempotency hit -> skipped
- outside-window -> blocked
- exit 0 -> done + last_migrated_sha bumped
- exit !=0 -> failed + tenant paused
- timeout -> timedout + tenant paused

Snapshot + subprocess are stubbed so tests don't shell out to real
binaries. The fake JobStore tracks all SQL-shaped calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import patch

import pytest

from migration_runner.db import JobRow
from migration_runner.runner import (
    POLL_INTERVAL_SECONDS,
    RunResult,
    Runner,
    classify_exit,
    compute_backoff_seconds,
)
from migration_runner.snapshot import SnapshotResult


class FakeStore:
    """Records every call without touching Postgres. The runner only
    cares about side-effects, not return values."""

    def __init__(self, job: Optional[JobRow]) -> None:
        self.job = job
        self.calls: list[tuple[str, tuple]] = []
        self._cursor_obj = object()

    def cursor(self):
        store = self

        class _CM:
            def __enter__(_self):  # noqa: N805
                return store._cursor_obj  # noqa: SLF001

            def __exit__(_self, *a):  # noqa: ARG002, N805
                return None

        return _CM()

    def _record(self, name: str, *args) -> None:
        self.calls.append((name, args))

    def claim_next_job(self, _cur) -> Optional[JobRow]:
        self._record('claim_next_job')
        j = self.job
        self.job = None  # one-shot — next iteration is idle
        return j

    def transition_to_skipped(self, _cur, job_id: str) -> None:
        self._record('transition_to_skipped', job_id)

    def transition_to_blocked(self, _cur, job_id: str, blocked_until=None) -> None:
        self._record('transition_to_blocked', job_id, blocked_until)

    def finalize_done(self, _cur, job_id, tenant_id, target_sha) -> None:
        self._record('finalize_done', job_id, tenant_id, target_sha)

    def finalize_failed(self, _cur, job_id, tenant_id, *, status, error_excerpt) -> None:
        self._record('finalize_failed', job_id, tenant_id, status, error_excerpt[:40])

    def retry_transient(self, _cur, job_id, *, backoff_seconds, error_excerpt) -> None:
        self._record('retry_transient', job_id, backoff_seconds, error_excerpt[:40])

    def record_heartbeat(self, _cur, _job_id):
        return 'running'

    def write_snapshot_id(self, _cur, job_id, snapshot_id) -> None:
        self._record('write_snapshot_id', job_id, snapshot_id)


def _mk_job(**overrides) -> JobRow:
    base = dict(
        id='job-uuid',
        tenant_id='tenant-uuid',
        tenant_slug='acme',
        tenant_db_name='acme',
        target_sha='sha-new',
        timeout_minutes=30,
        retry_count=0,
        maintenance_window='* * * * *',  # always open
        tz='UTC',
        last_migrated_sha='sha-old',
        wave='canary',
    )
    base.update(overrides)
    return JobRow(**base)


def _fake_snapshot(*, tenant_slug, db_name):
    return SnapshotResult(snapshot_id='backup-tag', elapsed_seconds=0.0)


class FakeProc:
    """subprocess.Popen stand-in with scripted exit code + stderr."""

    def __init__(self, exit_code: int, stderr: bytes = b'', timeout: bool = False) -> None:
        self.returncode = exit_code
        self._stderr = stderr
        self._stdout = b''
        self._timeout = timeout
        self.pid = 42_424
        self.terminated = False
        self.killed = False

    def communicate(self, timeout: Optional[float] = None):  # noqa: ARG002
        if self._timeout:
            import subprocess

            self._timeout = False  # second call returns
            raise subprocess.TimeoutExpired(cmd='odoo', timeout=timeout)
        return self._stdout, self._stderr

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class TestRunOnceIdle:
    def test_returns_idle_when_no_job(self) -> None:
        store = FakeStore(job=None)
        runner = Runner(store, snapshot_fn=_fake_snapshot, sleep_fn=lambda _s: None)
        result = runner.run_once()
        assert result.status == 'idle'
        assert result.job_id is None


class TestRunOnceSkipped:
    def test_idempotency_hit(self) -> None:
        job = _mk_job(last_migrated_sha='sha-new')  # already at target
        store = FakeStore(job=job)
        runner = Runner(store, snapshot_fn=_fake_snapshot, sleep_fn=lambda _s: None)
        result = runner.run_once()
        assert result.status == 'skipped'
        assert ('transition_to_skipped', ('job-uuid',)) in store.calls
        # Snapshot never taken.
        assert not any(c[0] == 'write_snapshot_id' for c in store.calls)


class TestRunOnceBlocked:
    def test_outside_window(self) -> None:
        # Window: every day at 02:00 ONLY. We're in 'noon UTC'
        # territory at test time.
        job = _mk_job(maintenance_window='0 2 * * *', tz='UTC')
        store = FakeStore(job=job)
        # Pin clock to 12:00 UTC.
        with patch(
            'migration_runner.runner.utcnow',
            return_value=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
        ):
            runner = Runner(store, snapshot_fn=_fake_snapshot, sleep_fn=lambda _s: None)
            result = runner.run_once()
        assert result.status == 'blocked'
        # Proper hot-loop fix: transition_to_blocked now takes a
        # `blocked_until` arg = next eligible firing. For cron='0 2 * * *'
        # at 12:00 UTC, the next firing is 02:00 the NEXT day = 14h ahead.
        blocked_calls = [c for c in store.calls if c[0] == 'transition_to_blocked']
        assert len(blocked_calls) == 1
        _, args = blocked_calls[0]
        job_id, blocked_until = args
        assert job_id == 'job-uuid'
        assert blocked_until == datetime(2026, 5, 24, 2, 0, tzinfo=timezone.utc)


class TestRunOnceHappyPath:
    def test_exit_0_finalises_done(self) -> None:
        job = _mk_job()
        store = FakeStore(job=job)
        proc = FakeProc(exit_code=0)
        with patch('subprocess.Popen', return_value=proc):
            runner = Runner(
                store,
                snapshot_fn=_fake_snapshot,
                sleep_fn=lambda _s: None,
                odoo_invocation=['/bin/true'],  # never actually invoked
            )
            result = runner.run_once()
        assert result.status == 'done'
        assert any(c[0] == 'finalize_done' for c in store.calls)
        # Snapshot wrote.
        assert ('write_snapshot_id', ('job-uuid', 'backup-tag')) in store.calls

    def test_exit_nonzero_finalises_failed(self) -> None:
        job = _mk_job()
        store = FakeStore(job=job)
        proc = FakeProc(exit_code=2, stderr=b'AssertionError: cost_center_id is null')
        with patch('subprocess.Popen', return_value=proc):
            runner = Runner(
                store,
                snapshot_fn=_fake_snapshot,
                sleep_fn=lambda _s: None,
                odoo_invocation=['/bin/false'],
            )
            result = runner.run_once()
        assert result.status == 'failed'
        failed = [c for c in store.calls if c[0] == 'finalize_failed']
        assert len(failed) == 1
        # error_excerpt contains the stderr tail.
        assert 'AssertionError' in failed[0][1][3]

    def test_timeout_finalises_timedout(self) -> None:
        job = _mk_job(timeout_minutes=1)
        store = FakeStore(job=job)
        proc = FakeProc(exit_code=-15, timeout=True)
        with patch('subprocess.Popen', return_value=proc):
            runner = Runner(
                store,
                snapshot_fn=_fake_snapshot,
                sleep_fn=lambda _s: None,
                odoo_invocation=['/bin/sleep', '120'],
            )
            result = runner.run_once()
        assert result.status == 'timedout'
        failed = [c for c in store.calls if c[0] == 'finalize_failed']
        assert failed and failed[0][1][2] == 'timedout'


class TestClassifyExit:
    def test_zero_is_done(self) -> None:
        assert classify_exit(0, retry_count=0) == 'done'

    def test_transient_signals_are_retry_under_cap(self) -> None:
        assert classify_exit(143, retry_count=0) == 'retry'
        assert classify_exit(137, retry_count=1) == 'retry'

    def test_terminal_at_retry_cap(self) -> None:
        assert classify_exit(143, retry_count=2) == 'failed'

    def test_unknown_failure_is_terminal(self) -> None:
        assert classify_exit(2, retry_count=0) == 'failed'


class TestBackoff:
    @pytest.mark.parametrize(
        ('retry_count', 'expected'),
        [
            (0, 300),  # 5 min
            (1, 1_200),  # 20 min
            (2, 2_700),  # 45 min
        ],
    )
    def test_5_20_45_minutes(self, retry_count: int, expected: int) -> None:
        assert compute_backoff_seconds(retry_count) == expected


class TestRunForeverSleepCases:
    """Regression: blocked-status hot-loop. Pre-fix, run_forever() only
    slept on 'idle' so the daemon re-claimed the same window-blocked
    job ~70 ops/sec. After the fix, 'blocked' also triggers a sleep."""

    def _make_runner_returning(self, statuses: list[str]) -> tuple[Runner, list[float]]:
        sleeps: list[float] = []
        results = iter([RunResult(job_id=f'job-{i}', status=s) for i, s in enumerate(statuses)])
        store = FakeStore(job=None)
        runner = Runner(store, snapshot_fn=_fake_snapshot, sleep_fn=sleeps.append)

        def stop_after_n_iterations(_self) -> RunResult:
            try:
                return next(results)
            except StopIteration:
                raise KeyboardInterrupt  # bail out of run_forever cleanly

        runner.run_once = stop_after_n_iterations.__get__(runner)
        return runner, sleeps

    def test_blocked_status_triggers_sleep(self) -> None:
        runner, sleeps = self._make_runner_returning(['blocked'])
        with pytest.raises(KeyboardInterrupt):
            runner.run_forever()
        assert sleeps == [POLL_INTERVAL_SECONDS], \
            f'blocked outcome should sleep POLL_INTERVAL once, got {sleeps}'

    def test_idle_status_triggers_sleep(self) -> None:
        runner, sleeps = self._make_runner_returning(['idle'])
        with pytest.raises(KeyboardInterrupt):
            runner.run_forever()
        assert sleeps == [POLL_INTERVAL_SECONDS]

    def test_done_status_does_not_sleep(self) -> None:
        # Terminal happy-path: keep draining the queue, don't sleep.
        runner, sleeps = self._make_runner_returning(['done'])
        with pytest.raises(KeyboardInterrupt):
            runner.run_forever()
        assert sleeps == [], f'done outcome should not sleep, got {sleeps}'


class TestRetryPath:
    def test_transient_exit_triggers_retry(self) -> None:
        job = _mk_job()
        store = FakeStore(job=job)
        proc = FakeProc(exit_code=143, stderr=b'sigterm from k8s eviction')
        with patch('subprocess.Popen', return_value=proc):
            runner = Runner(
                store,
                snapshot_fn=_fake_snapshot,
                sleep_fn=lambda _s: None,
                odoo_invocation=['/bin/true'],
            )
            result = runner.run_once()
        assert result.status == 'retry'
        retry = [c for c in store.calls if c[0] == 'retry_transient']
        assert retry and retry[0][1][1] == 300  # first backoff = 5 min
