"""Rollback helper — restore a tenant DB from its pre-migration
snapshot when a migration succeeded at the schema level but broke
the tenant in production.

Composes with the existing rollback-prod.yml: that workflow rolls
back the IMAGE; this module rolls back the DATA. Together they
restore a tenant to "the state it was in before migration job X".

Inputs (positional): job_id (uuid). Looks up:
- snapshot_id from tenant_migration_jobs
- db_name + slug + previous_last_migrated_sha from tenants
- pre-migration image digest from the `tenant_image_pins` table
  (Phase 4.1 enterprise-v1 surface — not added in this commit's
  schema; rollback assumes the operator has pinned the previous
  digest separately and only needs the DB restore).

Side effects:
1. Stops the tenant from serving traffic (sets state='suspended').
2. Calls pgBackRest restore on the snapshot tag.
3. Reverts tenants.last_migrated_sha (we don't have history here so
   we ARGUMENT a previous_sha).
4. Re-enables the tenant (state='active') after restore.
5. Records an audit event 'tenant.migration_rolled_back'.

Idempotency: rollback is operator-initiated and assumed to be a
one-shot. The runner does NOT auto-rollback on failure — Tier 5
acceptance criteria explicitly call for operator action only.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class RollbackError(RuntimeError):
    """Rollback couldn't complete."""


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """Inputs the operator workflow passes to rollback.run()."""

    job_id: str
    tenant_id: str
    tenant_db_name: str
    snapshot_id: str
    previous_sha: Optional[str]
    reason: str
    actor: str


@dataclass(frozen=True, slots=True)
class RollbackResult:
    job_id: str
    snapshot_id: str
    status: str  # 'ok' | 'snapshot_missing' | 'restore_failed'


def _pgrestore_argv(snapshot_key: str, db_name: str) -> list[str]:
    """Wrap pgrestore-snapshot.sh in flyctl-ssh to the Postgres app.

    Mirrors :func:`_pgbackrest_argv`'s pattern — the wrapper script
    lives on the Postgres machine (where pg_restore + S3 creds are);
    we delegate execution via SSH.
    """
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    remote_cmd = f'/usr/local/bin/pgrestore-snapshot.sh {snapshot_key} {db_name}'
    return ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd]


def _rollback_via_pgrestore(
    plan: 'RollbackPlan',
    *,
    dry_run: bool,
    subprocess_runner=subprocess.run,
) -> 'RollbackResult':
    """Per-tenant rollback via pg_restore from an S3 dump.

    The snapshot_id is an S3 key produced by ``pgdump-snapshot.sh``.
    We delegate the restore to the Postgres machine, which streams the
    dump from S3 into ``pg_restore --clean --if-exists -d <db>``. Only
    the target tenant's database is rewritten — other tenants on the
    same cluster are untouched (Tier 5 Item 2 acceptance property).

    PGBACKREST_DRY_RUN=true short-circuits the destructive restore but
    still logs the would-be argv — same gating discipline as the
    cluster-wide pgbackrest path so drills exercise the orchestration
    without touching tenant data.
    """
    argv = _pgrestore_argv(plan.snapshot_id, plan.tenant_db_name)
    if dry_run:
        logger.info(
            'PGBACKREST_DRY_RUN=true; skipping destructive pg_restore. '
            'Would have run: %s',
            ' '.join(argv),
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='ok',
        )
    try:
        subprocess_runner(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=2 * 60 * 60,  # 2h cap; restore can be slow on large tenants
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            'pg_restore failed exit=%d stderr=%s',
            exc.returncode,
            (exc.stderr or '')[-2000:],
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='restore_failed',
        )
    except subprocess.TimeoutExpired as exc:
        raise RollbackError(f'pg_restore timed out after 2h: {exc}') from exc

    logger.info('rollback complete (pgdump) job=%s dry_run=%s', plan.job_id, dry_run)
    return RollbackResult(
        job_id=plan.job_id,
        snapshot_id=plan.snapshot_id,
        status='ok',
    )


def _pgbackrest_argv(*args: str) -> list[str]:
    """Wrap a pgbackrest command in flyctl-ssh to odoo-saas-postgres.

    The migration-runner image does NOT bundle pgbackrest itself —
    the stanza config + S3 creds + Postgres data dir all live on the
    odoo-saas-postgres machine. We SSH-delegate the pgbackrest call
    so it runs where the data + creds are.

    Env knobs:
      - ``PGBACKREST_SSH_APP`` overrides the target app name
        (default: odoo-saas-postgres). Useful for staging.
      - ``FLY_API_TOKEN`` must be set with ssh permission on the
        target app (provisioned via FLY_SSH_TOKEN_POSTGRES secret).
    """
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    remote_cmd = 'gosu postgres pgbackrest ' + ' '.join(args)
    return ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd]


def run(
    plan: RollbackPlan,
    *,
    pgbackrest_stanza: Optional[str] = None,
    subprocess_runner=subprocess.run,
) -> RollbackResult:
    """Restore the tenant DB from its pre-migration snapshot tag.

    Restore is SSH-delegated to the Postgres machine (see
    ``_pgbackrest_argv``) so we don't need pgbackrest + stanza config
    + S3 creds duplicated on the runner.

    Two recovery strategies, picked by snapshot_id shape:
      - real tag (e.g. ``20260525-220000F``): ``--set=<tag> restore``.
      - sentinel ``no-snapshot-<ts>`` (SNAPSHOT_MODE=skip path): fall
        back to point-in-time recovery via ``--target-time``. The
        target time isn't known here — caller can pass it via
        ``ROLLBACK_TARGET_TIME`` env (ISO 8601) or omit, in which
        case we return ``status='snapshot_missing'`` because there's
        no safe default.

    Set ``PGBACKREST_DRY_RUN=true`` to short-circuit AFTER the
    pgbackrest reachability check (`info`) but BEFORE the restore
    invocation. Returns ``status='ok'`` and logs the would-be
    restore argv. Critical for drilling the chain against a live
    Postgres without disruption — pgbackrest itself does NOT
    support ``--dry-run`` on the restore command (it's a backup-only
    flag), so we have to gate at the orchestration layer.

    Assumes a separate process / step has already suspended the tenant
    (this module shouldn't decide tenant lifecycle on its own).
    """
    stanza = pgbackrest_stanza or os.environ.get('PGBACKREST_STANZA', 'shared')
    dry_run = os.environ.get('PGBACKREST_DRY_RUN', '').lower() in ('1', 'true', 'yes')

    logger.info(
        'rollback start job=%s tenant=%s snapshot=%s dry_run=%s',
        plan.job_id,
        plan.tenant_db_name,
        plan.snapshot_id,
        dry_run,
    )

    # Tier 5 Item 2: per-tenant pg_restore path. Selected by
    # snapshot_id prefix (`pgdump/<slug>/...`). Restores only the
    # target tenant's DB; other tenants on the cluster untouched.
    # Spec: docs/superpowers/specs/2026-05-27-per-tenant-restore-design.md
    if plan.snapshot_id.startswith('pgdump/'):
        return _rollback_via_pgrestore(plan, dry_run=dry_run, subprocess_runner=subprocess_runner)

    # Detect the sentinel-snapshot case (SNAPSHOT_MODE was 'skip' when
    # the migration ran). Need a target-time fallback or we can't
    # restore.
    is_sentinel = plan.snapshot_id.startswith('no-snapshot-')
    target_time = os.environ.get('ROLLBACK_TARGET_TIME') if is_sentinel else None
    if is_sentinel and not target_time:
        logger.error(
            'job %s has sentinel snapshot_id=%s and no ROLLBACK_TARGET_TIME — cannot restore',
            plan.job_id,
            plan.snapshot_id,
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='snapshot_missing',
        )

    # Step 1: verify pgbackrest is reachable AND the snapshot tag exists
    # (only meaningful for the non-sentinel path; sentinel uses
    # target-time and trusts WAL archival).
    try:
        info = subprocess_runner(
            _pgbackrest_argv(f'--stanza={stanza}', 'info', '--output=json'),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RollbackError(
            f'pgbackrest info exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    except FileNotFoundError as exc:  # flyctl missing
        raise RollbackError(
            'flyctl not on PATH — install in migration-runner Dockerfile'
        ) from exc
    if not is_sentinel and plan.snapshot_id not in (info.stdout or ''):
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='snapshot_missing',
        )

    # Step 2: restore. pgBackRest restore is destructive — it stops
    # Postgres and replays from S3 into the data dir. Tier 5 runbook
    # covers tenant suspension + Postgres restart; here we issue the
    # command. PGBACKREST_DRY_RUN=true short-circuits AFTER info but
    # BEFORE restore — pgbackrest's `--dry-run` flag is backup-only,
    # so we gate at the orchestration layer.
    restore_args: list[str] = [f'--stanza={stanza}', '--delta']
    if is_sentinel:
        restore_args.extend(['--type=time', f'--target={target_time}'])
    else:
        restore_args.extend(['--set', plan.snapshot_id])
    restore_args.append('restore')

    if dry_run:
        logger.info(
            'PGBACKREST_DRY_RUN=true; skipping destructive restore. '
            'Would have run: %s',
            ' '.join(_pgbackrest_argv(*restore_args)),
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='ok',
        )

    try:
        subprocess_runner(
            _pgbackrest_argv(*restore_args),
            check=True,
            capture_output=True,
            text=True,
            timeout=2 * 60 * 60,  # 2h cap
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            'pgbackrest restore failed exit=%d stderr=%s',
            exc.returncode,
            (exc.stderr or '')[-2000:],
        )
        return RollbackResult(
            job_id=plan.job_id,
            snapshot_id=plan.snapshot_id,
            status='restore_failed',
        )
    except subprocess.TimeoutExpired as exc:
        raise RollbackError(f'pgbackrest restore timed out after 2h: {exc}') from exc

    logger.info('rollback complete job=%s dry_run=%s', plan.job_id, dry_run)
    return RollbackResult(
        job_id=plan.job_id,
        snapshot_id=plan.snapshot_id,
        status='ok',
    )


# ── CLI entrypoint (used by rollback-prod.yml `tenant-restore` step) ───

def _lookup_plan(cur, job_id: str, previous_sha: str, actor: str) -> RollbackPlan:
    """Build a RollbackPlan from the job row + tenant row.

    Raises RollbackError if the job is unknown or the snapshot wasn't
    recorded (pre-Tier-7 jobs without snapshot_id can't be rolled back
    this way)."""
    cur.execute(
        """
        SELECT j.id::text, j.tenant_id::text, t.db_name, t.slug, j.snapshot_id
        FROM tenant_migration_jobs j
        JOIN tenants t ON t.id = j.tenant_id
        WHERE j.id = %s
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RollbackError(f'job {job_id} not found')
    _, tenant_id, db_name, slug, snapshot_id = row
    if not snapshot_id:
        raise RollbackError(
            f'job {job_id} has no snapshot_id — cannot restore from pgbackrest'
        )
    return RollbackPlan(
        job_id=job_id,
        tenant_id=tenant_id,
        tenant_db_name=db_name,
        snapshot_id=snapshot_id,
        previous_sha=previous_sha,
        reason=f'operator rollback to {previous_sha[:7]}',
        actor=actor,
    )


def _finalize_ok(cur, plan: RollbackPlan) -> None:
    """Revert tenants.last_migrated_sha, flip the job to 'rolled_back',
    and write the audit row. Single transaction so partial failures
    don't leave inconsistent state."""
    cur.execute(
        """
        UPDATE tenants
        SET last_migrated_sha = %s, updated_at = now()
        WHERE id = %s
        """,
        (plan.previous_sha, plan.tenant_id),
    )
    cur.execute(
        """
        UPDATE tenant_migration_jobs
        SET status = 'cancelled',
            finished_at = now(),
            error_excerpt = %s
        WHERE id = %s
        """,
        (f'rolled back to {plan.previous_sha[:7]} by {plan.actor}', plan.job_id),
    )
    # Build the payload as a JSON string in Python and cast to jsonb
    # in the SQL — jsonb_build_object with bare %s params trips
    # psycopg's type inference ("could not determine data type of
    # parameter $N") because Postgres can't statically resolve each
    # member's type without explicit casts on every argument. Building
    # the string client-side sidesteps the whole problem.
    import json as _json

    payload_str = _json.dumps(
        {
            'job_id': plan.job_id,
            'snapshot_id': plan.snapshot_id,
            'previous_sha': plan.previous_sha,
            'outcome': 'ok',
        }
    )
    cur.execute(
        """
        INSERT INTO saas_audit.event
            (actor_kind, actor_name, action, target_kind, target_id, sha, reason, payload)
        VALUES
            ('human', %s, 'tenant.migration_rolled_back', 'tenant', %s, %s, %s, %s::jsonb)
        """,
        (
            plan.actor,
            plan.tenant_id,
            plan.previous_sha,
            plan.reason,
            payload_str,
        ),
    )


def cli(argv: Optional[list[str]] = None) -> int:
    """`python -m migration_runner.rollback <job_id> <previous_sha>`

    Reads CONTROL_PLANE_PG_DSN from env, opens a single connection,
    looks up the migration job + tenant, runs the pgBackRest restore
    via `run()`, and on success reverts tenants.last_migrated_sha +
    writes a saas_audit.event row. All DB writes are committed in one
    transaction so the audit row + sha revert are atomic.

    Exit codes:
      0  — restore + finalize succeeded.
      1  — usage error (missing args).
      2  — RollbackError raised (job missing, snapshot missing, etc).
      3  — pgbackrest restore returned status='restore_failed'.
      4  — pgbackrest snapshot tag absent (status='snapshot_missing').
    """
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print(
            'usage: python -m migration_runner.rollback <job_id> <previous_sha>',
            file=sys.stderr,
        )
        return 1
    job_id, previous_sha = argv
    actor = os.environ.get('ROLLBACK_ACTOR') or os.environ.get('GITHUB_ACTOR', 'unknown')

    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )

    dsn = os.environ.get('CONTROL_PLANE_PG_DSN')
    if not dsn:
        print('CONTROL_PLANE_PG_DSN not set', file=sys.stderr)
        return 1

    # Local import so unit tests can stub the module without pulling
    # psycopg. Matches the same import pattern as JobStore._connect.
    import psycopg

    conn = psycopg.connect(dsn, autocommit=False)
    try:
        with conn.cursor() as cur:
            try:
                plan = _lookup_plan(cur, job_id, previous_sha, actor)
            except RollbackError as exc:
                logger.error('%s', exc)
                conn.rollback()
                return 2
        # Snapshot restore happens OUTSIDE the DB transaction — it
        # shells out to pgbackrest and can take minutes/hours. We
        # also commit the lookup-side read-txn first so the pgbackrest
        # subprocess doesn't hold a transaction open against Neon.
        conn.commit()
        result = run(plan)
        if result.status == 'snapshot_missing':
            logger.error('snapshot %s missing — aborting', plan.snapshot_id)
            return 4
        if result.status == 'restore_failed':
            logger.error('pgbackrest restore failed for snapshot %s', plan.snapshot_id)
            return 3
        with conn.cursor() as cur:
            _finalize_ok(cur, plan)
        conn.commit()
    finally:
        conn.close()
    logger.info(
        'rollback OK job=%s tenant=%s previous_sha=%s',
        plan.job_id,
        plan.tenant_db_name,
        plan.previous_sha,
    )
    return 0


if __name__ == '__main__':
    import sys

    sys.exit(cli())
