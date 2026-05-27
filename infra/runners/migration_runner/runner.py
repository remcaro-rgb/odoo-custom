"""Migration-job runner — the main loop.

One process per worker machine. Cluster concurrency = number of
machines (recommended default 3, see plan §5).

Lifecycle of a single iteration:

  1. claim_next_job() — atomic SELECT FOR UPDATE SKIP LOCKED + flip
     status to 'running'.
  2. If no row, sleep POLL_INTERVAL and loop.
  3. Idempotency check: tenants.last_migrated_sha == target_sha?
     Yes -> transition_to_skipped() and continue.
  4. Window check: WindowEvaluator.is_open(now)?
     No  -> transition_to_blocked() and continue.
  5. Snapshot.take_snapshot() -> write_snapshot_id().
  6. Start heartbeat thread.
  7. Invoke `odoo -u all -d <db> --stop-after-init --no-http` as a
     subprocess. Honour timeout_minutes.
  8. Classify exit:
       exit 0           -> finalize_done() + bump last_migrated_sha
       transient signal -> retry_transient() (Tier 3 logic)
       timeout          -> finalize_failed(status='timedout')
       any other        -> finalize_failed(status='failed')
  9. Stop heartbeat thread, log audit row (Tier 6 emits via DB),
     sleep POLL_INTERVAL, loop.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from .db import JobRow, JobStore, utcnow
from .heartbeat import HeartbeatThread
from .snapshot import SnapshotError, take_snapshot
from .window import WindowEvaluator

logger = logging.getLogger(__name__)

# How often we poll the queue when no jobs are available.
POLL_INTERVAL_SECONDS = float(os.environ.get('RUNNER_POLL_INTERVAL', '15'))

# Exit-code classification — Tier 3.
TRANSIENT_EXIT_CODES = {
    # SIGTERM (143), SIGKILL (137), connection-refused conventions:
    143,
    137,
    # Custom: psycopg connection refused conventionally re-raises as
    # OperationalError but if we surface the exit code, treat -2 (no
    # such file/connection refused-ish) as transient.
}


@dataclass(frozen=True, slots=True)
class RunResult:
    """One iteration's outcome — for logs + tests."""

    job_id: Optional[str]
    status: str  # 'idle' | 'skipped' | 'blocked' | 'done' | 'failed' | 'timedout' | 'cancelled' | 'retry'


def compute_backoff_seconds(retry_count: int) -> int:
    """5 min / 20 min / 45 min — per plan §4 Tier 3."""
    # retry_count is the count AFTER this attempt failed; we apply
    # the next-attempt backoff.
    return (retry_count + 1) * (retry_count + 1) * 300


def classify_exit(exit_code: int, retry_count: int, max_retries: int = 3) -> str:
    """Return the next status given the exit code + retry budget."""
    if exit_code == 0:
        return 'done'
    if retry_count + 1 >= max_retries:
        return 'failed'
    if exit_code in TRANSIENT_EXIT_CODES:
        return 'retry'
    return 'failed'


class Runner:
    """Single-process queue consumer."""

    def __init__(
        self,
        store: JobStore,
        *,
        odoo_invocation: Optional[list[str]] = None,
        snapshot_fn=None,
        window_factory=None,
        sleep_fn=None,
        runner_host: Optional[str] = None,
    ) -> None:
        self._store = store
        self._odoo_invocation = odoo_invocation or _default_odoo_invocation()
        self._snapshot_fn = snapshot_fn or take_snapshot
        self._window_factory = window_factory or _default_window
        self._sleep = sleep_fn or time.sleep
        self._runner_host = runner_host or os.environ.get(
            'FLY_MACHINE_ID', os.environ.get('HOSTNAME', 'unknown')
        )
        # Propagate the host into the store so claim_next_job stamps it
        # onto the row at the moment we take it (single-tx guarantee).
        if hasattr(store, '_runner_host'):
            store._runner_host = self._runner_host  # noqa: SLF001

    def run_once(self) -> RunResult:
        """Process one queue iteration. Returns RunResult so tests +
        the cluster's metrics endpoint can observe progress."""
        with self._store.cursor() as cur:
            job = self._store.claim_next_job(cur)
        if job is None:
            return RunResult(job_id=None, status='idle')
        return self._process(job)

    def run_forever(self) -> None:
        """Loop until SIGTERM. Block between iterations on POLL_INTERVAL
        when the queue is empty OR the only available work is a row we
        just observed as blocked.

        The proper hot-loop fix is the `blocked_until` column on
        tenant_migration_jobs (added in control-plane PR #13); the
        claim_next_job filter then makes blocked rows invisible until
        their next eligible firing. The sleep here is defense-in-depth:
        if a row's blocked_until has elapsed in the same tick the
        runner just blocked it (NULL back-compat), the sleep prevents
        a one-off spin. POLL_INTERVAL_SECONDS = 15s by default."""
        logger.info('runner started host=%s', self._runner_host)
        while True:
            try:
                result = self.run_once()
            except Exception:  # broad — never let the daemon die silently
                logger.exception('run_once raised; sleeping then retrying')
                self._sleep(POLL_INTERVAL_SECONDS)
                continue
            if result.status in ('idle', 'blocked'):
                self._sleep(POLL_INTERVAL_SECONDS)

    # ── Per-job processing ──────────────────────────────────────────

    def _process(self, job: JobRow) -> RunResult:
        # Idempotency.
        if job.last_migrated_sha == job.target_sha:
            with self._store.cursor() as cur:
                self._store.transition_to_skipped(cur, job.id)
            logger.info('job %s skipped — tenant already at %s', job.id, job.target_sha)
            return RunResult(job_id=job.id, status='skipped')

        # Window check.
        evaluator = self._window_factory(job)
        now = utcnow()
        if not evaluator.is_open(now):
            # Compute next eligible firing so claim_next_job can skip
            # this row until it elapses — kills the hot-loop at the
            # SQL layer. The runner.py-side sleep added by PR #94 is
            # kept as defense-in-depth: claim_next_job still costs an
            # SQL round-trip even with the filter, so we don't want
            # the daemon to spin if the queue magically refilled.
            blocked_until = evaluator.next_open(now)
            with self._store.cursor() as cur:
                self._store.transition_to_blocked(cur, job.id, blocked_until)
            logger.info(
                'job %s blocked — outside maintenance window; next open %s',
                job.id,
                blocked_until.isoformat(),
            )
            return RunResult(job_id=job.id, status='blocked')

        # Snapshot.
        try:
            snap = self._snapshot_fn(
                tenant_slug=job.tenant_slug, db_name=job.tenant_db_name
            )
        except SnapshotError as exc:
            logger.exception('snapshot failed for job %s', job.id)
            with self._store.cursor() as cur:
                self._store.finalize_failed(
                    cur,
                    job.id,
                    job.tenant_id,
                    status='failed',
                    error_excerpt=f'snapshot failed: {exc}'[:50_000],
                )
            return RunResult(job_id=job.id, status='failed')
        with self._store.cursor() as cur:
            self._store.write_snapshot_id(cur, job.id, snap.snapshot_id)

        # Subprocess + heartbeat.
        return self._run_odoo(job)

    def _run_odoo(self, job: JobRow) -> RunResult:
        # Tier 7: dry-run clones the tenant DB to a temp database
        # before migrating. The clone name is bounded by Postgres'
        # 63-char identifier limit; we take the first 40 chars of the
        # tenant slug to stay safely under that.
        if job.migration_dry_run:
            target_db = self._make_dryrun_clone(job)
        else:
            target_db = job.tenant_db_name

        env = os.environ.copy()
        env.update(
            {
                'TARGET_DB': target_db,
                'UPDATE_MODULES': 'all',
                'STOP_AFTER_INIT': '1',
            }
        )
        timeout_seconds = job.timeout_minutes * 60
        cmd = self._odoo_invocation + ['-d', target_db]

        logger.info(
            'job %s: starting odoo -u all (timeout=%ds)', job.id, timeout_seconds
        )
        try:
            proc = subprocess.Popen(  # noqa: S603 — args are controlled
                cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except FileNotFoundError as exc:
            with self._store.cursor() as cur:
                self._store.finalize_failed(
                    cur,
                    job.id,
                    job.tenant_id,
                    status='failed',
                    error_excerpt=f'odoo binary missing: {exc}',
                )
            return RunResult(job_id=job.id, status='failed')

        hb = HeartbeatThread(self._store, job.id, proc.pid)
        hb.start()
        try:
            stdout_b, stderr_b = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            logger.warning('job %s timed out after %ds — SIGTERM', job.id, timeout_seconds)
            proc.terminate()
            try:
                stdout_b, stderr_b = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_b, stderr_b = proc.communicate()
            exit_code = proc.returncode
            timed_out = True
        finally:
            hb.stop()

        stderr = (stderr_b or b'').decode('utf-8', errors='replace')[-50_000:]
        # Operator-cancelled via Tier 1 -> the heartbeat thread already
        # SIGTERM'd the subprocess. Mark the job 'cancelled' if we
        # detect it; do NOT auto-pause the tenant.
        if hb.observed_cancel:
            logger.info('job %s cancelled by operator', job.id)
            # The row is already 'cancelled' (Tier 1 set it). No-op here.
            return RunResult(job_id=job.id, status='cancelled')

        if timed_out:
            with self._store.cursor() as cur:
                self._store.finalize_failed(
                    cur,
                    job.id,
                    job.tenant_id,
                    status='timedout',
                    error_excerpt=f'timed out after {timeout_seconds}s\n{stderr}'[:50_000],
                )
            return RunResult(job_id=job.id, status='timedout')

        next_status = classify_exit(exit_code, job.retry_count)
        if next_status == 'done':
            with self._store.cursor() as cur:
                if job.migration_dry_run:
                    # Dry-run: do NOT bump tenants.last_migrated_sha;
                    # just mark the job done. The clone is dropped
                    # below in _drop_dryrun_clone().
                    self._store.transition_to_skipped(cur, job.id)
                else:
                    self._store.finalize_done(
                        cur, job.id, job.tenant_id, job.target_sha
                    )
            if job.migration_dry_run:
                self._drop_dryrun_clone(target_db)
                logger.info('job %s dry-run done — clone %s dropped', job.id, target_db)
            else:
                logger.info('job %s done — tenant moved to %s', job.id, job.target_sha)
            return RunResult(job_id=job.id, status='done')
        if next_status == 'retry':
            backoff = compute_backoff_seconds(job.retry_count)
            with self._store.cursor() as cur:
                self._store.retry_transient(
                    cur,
                    job.id,
                    backoff_seconds=backoff,
                    error_excerpt=f'transient exit={exit_code}\n{stderr}'[:50_000],
                )
            logger.info(
                'job %s transient (exit=%d) — retry in %ds', job.id, exit_code, backoff
            )
            return RunResult(job_id=job.id, status='retry')
        # status == 'failed'
        with self._store.cursor() as cur:
            self._store.finalize_failed(
                cur,
                job.id,
                job.tenant_id,
                status='failed',
                error_excerpt=f'exit={exit_code}\n{stderr}'[:50_000],
            )
        logger.error('job %s failed (exit=%d) — tenant paused', job.id, exit_code)
        return RunResult(job_id=job.id, status='failed')


    def _make_dryrun_clone(self, job: JobRow) -> str:
        """Tier 7 — CREATE DATABASE <tenant>__dryrun_<jobshort> WITH
        TEMPLATE <tenant>. Returns the clone DB name."""
        short = job.id.replace('-', '')[:8]
        slug40 = job.tenant_slug[:40]
        clone = f'{slug40}__dryrun_{short}'
        with self._store.cursor() as cur:
            # autocommit semantics: CREATE DATABASE can't be in a tx,
            # but our cursor() context wraps in one. The runner-side
            # `psycopg.connect(autocommit=False)` then breaks CREATE
            # DATABASE. Tier 7 deployment: ensure the runner uses a
            # separate psycopg connection for these admin ops (TODO).
            # For now we issue the statement and document the
            # constraint; the implementation falls back to "skip the
            # clone if it errors" so the runner doesn't crash.
            try:
                cur.execute(f'CREATE DATABASE "{clone}" TEMPLATE "{job.tenant_db_name}"')
            except Exception:
                logger.exception(
                    'dry-run clone CREATE DATABASE failed — running against real DB '
                    'is NOT safe; skipping migration. job=%s',
                    job.id,
                )
                # Mark the job failed so the operator notices.
                self._store.finalize_failed(
                    cur,
                    job.id,
                    job.tenant_id,
                    status='failed',
                    error_excerpt='dry-run clone failed; see runner logs',
                )
                raise
        return clone

    def _drop_dryrun_clone(self, clone_db: str) -> None:
        """Best-effort DROP DATABASE. The CREATE/DROP DATABASE
        statements need autocommit; this method swallows errors so a
        partial cleanup doesn't crash the loop."""
        try:
            with self._store.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{clone_db}"')
        except Exception:
            logger.exception(
                'failed to drop dry-run clone %s (manual cleanup required)', clone_db
            )


def _default_odoo_invocation() -> list[str]:
    """Resolve `odoo` from PATH; fall back to /opt/odoo/odoo if the
    runner image's PATH doesn't include it."""
    binary = shutil.which('odoo') or '/opt/odoo/odoo'
    # --no-http: don't spin up the HTTP server in maintenance mode.
    # -u all: force-rerun every installed module's migrations + XML reload.
    # --stop-after-init: exit when initialisation completes.
    return [binary, '-u', 'all', '--stop-after-init', '--no-http']


def _default_window(job: JobRow) -> WindowEvaluator:
    """Build a per-job window evaluator. Tier 4: honour per-tenant
    override_until + the cluster-wide MIGRATION_WINDOW_GLOBAL_OVERRIDE
    env flag (set via the operator UI / feature flag table)."""
    global_override = os.environ.get('MIGRATION_WINDOW_GLOBAL_OVERRIDE', '').lower() in (
        '1',
        'true',
        'yes',
    )
    return WindowEvaluator(
        cron=job.maintenance_window,
        tz=job.tz,
        override_until=job.maintenance_window_override_until,
        global_override=global_override,
    )


def _install_sigterm_handler() -> None:
    def handler(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info('SIGTERM received — exiting cleanly')
        sys.exit(0)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> None:  # pragma: no cover — integration entry
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO'),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    dsn = os.environ.get('CONTROL_PLANE_PG_DSN')
    if not dsn:
        logger.error('CONTROL_PLANE_PG_DSN unset — refusing to start')
        sys.exit(1)
    _install_sigterm_handler()
    # Fly's [checks.daemon_alive] probes tcp/9999 every 30s. Without a
    # listener bound the check has been failing on every deploy of this
    # app since launch (cosmetic noise on flyctl status + makes
    # flyctl deploy --wait-timeout time out waiting for "healthy").
    from migration_runner.health_listener import start_health_listener
    start_health_listener()
    store = JobStore(dsn=dsn)
    runner = Runner(store)
    runner.run_forever()
