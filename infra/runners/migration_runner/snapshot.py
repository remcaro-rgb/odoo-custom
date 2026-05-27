"""Snapshot helper — wraps pgBackRest for the pre-migration safety net.

Four implementation strategies, selected via SNAPSHOT_MODE env:

- ``cli`` — call ``pgbackrest --stanza=<stanza> backup --type=incr``
  directly. Used when the runner has direct shell access to a node where
  pgbackrest is configured (Railway: backups run inside the postgres
  service; Fly: a sidecar). Cluster-wide backup.
- ``ssh`` — flyctl-ssh into ``odoo-saas-postgres`` and run the same
  ``pgbackrest backup`` command there. Used when the runner runs on a
  *different* Fly app than Postgres (the common prod case — the
  migration-runner image does NOT bundle pgbackrest or the stanza
  config; SSH-delegation keeps that surface on Postgres alone).
  Requires ``flyctl`` on PATH and ``FLY_API_TOKEN`` with ssh
  permission on ``odoo-saas-postgres``. Cluster-wide backup.
- ``pgdump`` — flyctl-ssh into the Postgres machine and run the
  ``/usr/local/bin/pgdump-snapshot.sh`` wrapper. Logical, *per-tenant*
  dump uploaded to S3 under ``pgdump/<tenant>/<ts>.dump``. Rollback
  via the matching ``pgrestore-snapshot.sh`` wrapper drops + reloads
  only the target tenant's database, leaving other tenants untouched.
  This is the Tier 5 Item 2 path (selective rollback).
  Spec: docs/superpowers/specs/2026-05-27-per-tenant-restore-design.md
- ``http`` — POST to the existing ``saas_filestore_backup`` HTTP
  endpoint (HMAC-signed). Used when there's a dedicated backup
  service.

All four return a ``snapshot_id`` (an opaque token — for ``cli``/
``ssh`` it's the pgbackrest backup label; for ``pgdump`` it's the S3
key under ``pgdump/...``) that the rollback path consumes and
dispatches by shape.

If ``SNAPSHOT_MODE=skip`` the call is a no-op returning a sentinel
``no-snapshot-<timestamp>`` string — used in tests and in CI smokes
where pgBackRest isn't wired up yet. The sentinel signals to the
rollback path that point-in-time-recovery (``--target-time``) must
substitute for ``--set=<tag>``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class SnapshotError(RuntimeError):
    """Snapshot operation failed in a non-recoverable way."""


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    snapshot_id: str
    elapsed_seconds: float


def take_snapshot(
    *,
    tenant_slug: str,
    db_name: str,
    mode: Optional[str] = None,
    hmac_secret: Optional[str] = None,
    backup_service_url: Optional[str] = None,
    pgbackrest_stanza: Optional[str] = None,
) -> SnapshotResult:
    """Take a pre-migration snapshot. Returns the snapshot tag.

    Env-driven defaults so the runner just calls take_snapshot(slug, db).
    """
    mode = mode or os.environ.get('SNAPSHOT_MODE', 'skip')
    started = time.monotonic()
    if mode == 'skip':
        return SnapshotResult(
            snapshot_id=f'no-snapshot-{int(started)}',
            elapsed_seconds=0.0,
        )
    if mode == 'cli':
        stanza = pgbackrest_stanza or os.environ.get('PGBACKREST_STANZA', db_name)
        snapshot_id = _snapshot_via_cli(stanza)
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    if mode == 'ssh':
        # SSH into the Postgres machine (where pgbackrest is installed
        # + configured) and run the backup there. Matches the existing
        # pattern in pgbackrest-backup.yml — keeps stanza/config/S3
        # creds on the Postgres node, not duplicated to the runner.
        stanza = pgbackrest_stanza or os.environ.get('PGBACKREST_STANZA', 'shared')
        snapshot_id = _snapshot_via_ssh(stanza)
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    if mode == 'pgdump':
        # Per-tenant logical dump → S3. SSH-delegated to the Postgres
        # machine where the wrapper script reads the existing pgbackrest
        # S3 creds. Returns an S3 key the rollback path uses to find +
        # replay the dump (drops + reloads only this tenant's DB, no
        # cluster-wide impact).
        snapshot_id = _snapshot_via_pgdump(tenant_slug=tenant_slug, db_name=db_name)
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    if mode == 'http':
        url = backup_service_url or os.environ.get('BACKUP_SERVICE_URL')
        secret = hmac_secret or os.environ.get('SAAS_BACKUP_HMAC_SECRET')
        if not url or not secret:
            raise SnapshotError(
                'SNAPSHOT_MODE=http requires BACKUP_SERVICE_URL + SAAS_BACKUP_HMAC_SECRET'
            )
        snapshot_id = _snapshot_via_http(
            url=url, secret=secret, tenant_slug=tenant_slug, db_name=db_name
        )
        return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
    raise SnapshotError(f'unknown SNAPSHOT_MODE={mode!r}')


def _snapshot_via_cli(stanza: str) -> str:
    """Run pgbackrest backup. Returns the backup label.

    The backup label is parsed from the last 'INFO: full|diff|incr
    backup: label = <label>' line in stdout.
    """
    try:
        result = subprocess.run(  # noqa: S603 — args are controlled
            ['pgbackrest', f'--stanza={stanza}', 'backup', '--type=incr'],
            check=True,
            capture_output=True,
            text=True,
            timeout=15 * 60,
        )
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(
            f'pgbackrest exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError('pgbackrest timed out after 15 min') from exc
    label = _parse_backup_label(result.stdout)
    if not label:
        raise SnapshotError(
            f'pgbackrest produced no backup label in stdout; tail={result.stdout[-2000:]}'
        )
    return label


def _snapshot_via_ssh(stanza: str) -> str:
    """Run pgbackrest backup over flyctl-ssh into odoo-saas-postgres.

    flyctl is invoked with ``--app`` so we don't depend on the runner's
    cwd being linked. Auth comes from ``FLY_API_TOKEN`` in env.
    """
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    remote_cmd = (
        f'gosu postgres pgbackrest --stanza={stanza} '
        '--log-level-console=info backup --type=incr'
    )
    try:
        result = subprocess.run(  # noqa: S603 — args are controlled
            ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd],
            check=True,
            capture_output=True,
            text=True,
            timeout=15 * 60,
        )
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(
            f'flyctl ssh pgbackrest exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError('flyctl ssh pgbackrest timed out after 15 min') from exc
    except FileNotFoundError as exc:  # flyctl binary missing in the image
        raise SnapshotError(
            'flyctl not on PATH — install in migration-runner Dockerfile'
        ) from exc
    label = _parse_backup_label(result.stdout)
    if not label:
        raise SnapshotError(
            f'pgbackrest produced no backup label in stdout; tail={result.stdout[-2000:]}'
        )
    return label


def _snapshot_via_pgdump(*, tenant_slug: str, db_name: str) -> str:
    """SSH-invoke the per-tenant pg_dump → S3 wrapper.

    The wrapper script lives in the Postgres image at
    ``/usr/local/bin/pgdump-snapshot.sh`` and prints
    ``SNAPSHOT_KEY=<s3-key>`` on its last line. We parse that key and
    return it as the snapshot_id.

    Tier 5 Item 2 path: returns an S3-key shape (``pgdump/<slug>/...``)
    that rollback.run() routes to the per-tenant pg_restore branch.
    """
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    remote_cmd = f'/usr/local/bin/pgdump-snapshot.sh {db_name} {tenant_slug}'
    try:
        result = subprocess.run(  # noqa: S603 — args are controlled
            ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd],
            check=True,
            capture_output=True,
            text=True,
            timeout=30 * 60,  # 30 min cap — pg_dump streaming for large tenants
        )
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(
            f'pgdump-snapshot exit {exc.returncode}: {(exc.stderr or "")[-2000:]}'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SnapshotError('pgdump-snapshot timed out after 30 min') from exc
    except FileNotFoundError as exc:
        raise SnapshotError(
            'flyctl not on PATH — install in migration-runner Dockerfile'
        ) from exc
    key = _parse_snapshot_key(result.stdout)
    if not key:
        raise SnapshotError(
            f'pgdump produced no SNAPSHOT_KEY line; tail={result.stdout[-2000:]}'
        )
    return key


def _parse_snapshot_key(stdout: str) -> Optional[str]:
    # Wrapper prints `SNAPSHOT_KEY=<key>` on the last line. Scan
    # bottom-up so any earlier diagnostic output doesn't confuse us.
    for line in reversed(stdout.splitlines()):
        marker = 'SNAPSHOT_KEY='
        if line.startswith(marker):
            return line[len(marker) :].strip()
    return None


def _parse_backup_label(stdout: str) -> Optional[str]:
    # pgbackrest's INFO line announcing the new backup. Two formats are
    # in the wild; we recognize both:
    #   pre-2.50:  "INFO: full backup: label = 20260523-220000F"
    #   2.50+ :    "INFO: new backup label = 20260524-065900F_20260527-065322I"
    # We scan bottom-up and prefer "new backup label" — that's the line
    # for THIS run; "last backup label" (also present in the log) is
    # the prior backup we're incremental-ing on top of, which would
    # produce a stale snapshot_id rollback can't find via `info` for
    # this job.
    markers = ('new backup label = ', 'backup: label = ')
    for line in reversed(stdout.splitlines()):
        for marker in markers:
            idx = line.find(marker)
            if idx >= 0:
                return line[idx + len(marker) :].strip()
    return None


def _snapshot_via_http(*, url: str, secret: str, tenant_slug: str, db_name: str) -> str:
    """POST to the backup service. HMAC body signing matches the
    pattern saas_provisioning_gateway uses."""
    import urllib.request

    payload = json.dumps(
        {
            'tenant_slug': tenant_slug,
            'db_name': db_name,
            'reason': 'pre-migration',
        }
    ).encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    req = urllib.request.Request(  # noqa: S310 — controlled URL
        url=url.rstrip('/') + '/snapshot',
        data=payload,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Signature': signature,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15 * 60) as resp:  # noqa: S310
            body = resp.read().decode('utf-8')
    except Exception as exc:  # urllib raises a number of distinct types
        raise SnapshotError(f'backup HTTP call failed: {exc}') from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f'backup service returned non-JSON: {body[:200]}') from exc
    snapshot_id = data.get('snapshot_id')
    if not snapshot_id or not isinstance(snapshot_id, str):
        raise SnapshotError(f'backup service response missing snapshot_id: {body[:200]}')
    return snapshot_id
