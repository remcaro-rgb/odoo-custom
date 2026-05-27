"""Tests for `rollback.run()` — the actual pgbackrest invocation path.

`run()` SSH-delegates `pgbackrest` calls to the Postgres machine via
`flyctl ssh console --app <pg> --command <pgbackrest ...>`. These
tests stub `subprocess_runner` so we don't shell out to a real
flyctl / pgbackrest.

Coverage:
- `_pgbackrest_argv` wraps args in flyctl-ssh correctly.
- run() with a real snapshot tag → info + restore with --set=<tag>.
- run() with sentinel snapshot_id + ROLLBACK_TARGET_TIME → restore
  with --target.
- run() with sentinel snapshot_id + no env → snapshot_missing.
- run() with PGBACKREST_DRY_RUN=true → restore command includes --dry-run.
- run() when flyctl is missing → RollbackError.
- run() when pgbackrest info returns non-matching tag → snapshot_missing.
- run() when restore subprocess returns non-zero → restore_failed.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from migration_runner.rollback import (
    RollbackError,
    RollbackPlan,
    RollbackResult,
    _pgbackrest_argv,
    run,
)


def _plan(*, snapshot_id: str = '20260525-220000F') -> RollbackPlan:
    return RollbackPlan(
        job_id='job-uuid',
        tenant_id='tenant-uuid',
        tenant_db_name='acme',
        snapshot_id=snapshot_id,
        previous_sha='886bf8b',
        reason='operator rollback',
        actor='octocat',
    )


@dataclass
class _ScriptedRunner:
    """subprocess.run stand-in. Each call pops the next scripted result."""

    scripted: list = field(default_factory=list)
    seen: list[list[str]] = field(default_factory=list)

    def __call__(self, argv, *, check=True, capture_output=False, text=False, timeout=None):
        self.seen.append(list(argv))
        if not self.scripted:
            return MagicMock(returncode=0, stdout='', stderr='')
        result = self.scripted.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _ok(stdout: str = '') -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ''
    return m


class TestPgbackrestArgvWrap:
    def test_wraps_in_flyctl_ssh(self) -> None:
        argv = _pgbackrest_argv('--stanza=shared', 'info', '--output=json')
        assert argv[0] == 'flyctl'
        assert argv[1:5] == ['ssh', 'console', '--app', 'odoo-saas-postgres']
        assert argv[5] == '--command'
        # All pgbackrest args joined into a single sh-quoted string.
        assert 'gosu postgres pgbackrest --stanza=shared info --output=json' in argv[6]

    def test_pg_app_overridable_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PGBACKREST_SSH_APP', 'staging-postgres')
        argv = _pgbackrest_argv('--stanza=shared', 'info')
        assert argv[4] == 'staging-postgres'


class TestRunHappyPath:
    def test_real_tag_uses_set_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('PGBACKREST_DRY_RUN', raising=False)
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='20260525-220000F')
        runner = _ScriptedRunner(
            scripted=[
                _ok(stdout='... 20260525-220000F ...'),  # info finds tag
                _ok(),  # restore
            ]
        )
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'ok'
        assert len(runner.seen) == 2
        # Both subprocess calls are flyctl-wrapped.
        for argv in runner.seen:
            assert argv[0] == 'flyctl'
        # Restore call uses --set=<tag>, not --target.
        restore_remote = runner.seen[1][6]
        assert '--set 20260525-220000F' in restore_remote
        assert '--target' not in restore_remote


class TestRunSentinelSnapshot:
    def test_sentinel_with_target_time_uses_target(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('ROLLBACK_TARGET_TIME', '2026-05-25 22:00:00+00')
        monkeypatch.delenv('PGBACKREST_DRY_RUN', raising=False)
        plan = _plan(snapshot_id='no-snapshot-1697')
        runner = _ScriptedRunner(scripted=[_ok(stdout='{}'), _ok()])
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'ok'
        restore_remote = runner.seen[1][6]
        assert '--type=time' in restore_remote
        assert "--target=2026-05-25 22:00:00+00" in restore_remote
        assert '--set' not in restore_remote

    def test_sentinel_without_target_returns_snapshot_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='no-snapshot-1697')
        runner = _ScriptedRunner()
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'snapshot_missing'
        # Early-return: no subprocess calls at all.
        assert runner.seen == []


class TestRunDryRun:
    def test_pgbackrest_dry_run_skips_destructive_restore(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # pgbackrest's --dry-run flag is backup-only; rollback.py
        # gates at the orchestration layer instead. With
        # PGBACKREST_DRY_RUN=true:
        #   1. info call still runs (pgbackrest reachability + tag check).
        #   2. restore call is SKIPPED — we early-return ok.
        monkeypatch.setenv('PGBACKREST_DRY_RUN', 'true')
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='20260525-220000F')
        # Only ONE scripted result needed — info. restore must not run.
        runner = _ScriptedRunner(scripted=[_ok(stdout='... 20260525-220000F ...')])
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'ok'
        # Exactly one subprocess call: the info probe. NO restore.
        assert len(runner.seen) == 1
        info_remote = runner.seen[0][6]
        assert ' info ' in info_remote
        assert 'restore' not in info_remote


class TestRunMissingFlyctl:
    def test_raises_rollback_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='20260525-220000F')
        runner = _ScriptedRunner(scripted=[FileNotFoundError('flyctl: not found')])
        with pytest.raises(RollbackError, match='flyctl not on PATH'):
            run(plan, subprocess_runner=runner)


class TestRunSnapshotTagMissing:
    def test_returns_snapshot_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='20260525-220000F')
        # info stdout doesn't contain the tag.
        runner = _ScriptedRunner(scripted=[_ok(stdout='{"backups": []}')])
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'snapshot_missing'
        # Only the info call ran — no restore attempt.
        assert len(runner.seen) == 1


class TestRunRestoreFailed:
    def test_returns_restore_failed_on_nonzero_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('ROLLBACK_TARGET_TIME', raising=False)
        plan = _plan(snapshot_id='20260525-220000F')
        called_process_error = subprocess.CalledProcessError(
            returncode=42, cmd='pgbackrest', stderr='restore failed: dummy'
        )
        runner = _ScriptedRunner(
            scripted=[_ok(stdout='... 20260525-220000F ...'), called_process_error]
        )
        result = run(plan, subprocess_runner=runner)
        assert result.status == 'restore_failed'


class TestRunPgdumpPath:
    """Tier 5 Item 2: per-tenant pg_restore branch, selected when
    snapshot_id starts with `pgdump/`. Does NOT call pgbackrest at all;
    only one subprocess call (the pgrestore-snapshot.sh wrapper)."""

    def _pgdump_plan(self) -> RollbackPlan:
        return RollbackPlan(
            job_id='job-uuid',
            tenant_id='tenant-uuid',
            tenant_db_name='acmesas2',
            snapshot_id='pgdump/acmesas2/20260527T120000Z.dump',
            previous_sha='886bf8b',
            reason='operator rollback',
            actor='octocat',
        )

    def test_dry_run_logs_but_does_not_call_wrapper(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('PGBACKREST_DRY_RUN', 'true')
        runner = _ScriptedRunner()
        result = run(self._pgdump_plan(), subprocess_runner=runner)
        assert result.status == 'ok'
        # Dry-run gates BEFORE any subprocess call.
        assert runner.seen == []

    def test_invokes_pgrestore_wrapper_with_key_and_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('PGBACKREST_DRY_RUN', raising=False)
        runner = _ScriptedRunner(scripted=[_ok()])
        result = run(self._pgdump_plan(), subprocess_runner=runner)
        assert result.status == 'ok'
        assert len(runner.seen) == 1
        argv = runner.seen[0]
        # flyctl-ssh wrap to the postgres app.
        assert argv[0] == 'flyctl'
        assert argv[1:5] == ['ssh', 'console', '--app', 'odoo-saas-postgres']
        assert argv[5] == '--command'
        # Wrapper invocation with key + db_name.
        assert argv[6] == (
            '/usr/local/bin/pgrestore-snapshot.sh '
            'pgdump/acmesas2/20260527T120000Z.dump acmesas2'
        )
        # We never touched pgbackrest in this branch.
        assert 'pgbackrest' not in ' '.join(argv)

    def test_uses_PGBACKREST_SSH_APP_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('PGBACKREST_SSH_APP', 'odoo-saas-postgres-staging')
        monkeypatch.delenv('PGBACKREST_DRY_RUN', raising=False)
        runner = _ScriptedRunner(scripted=[_ok()])
        run(self._pgdump_plan(), subprocess_runner=runner)
        argv = runner.seen[0]
        assert argv[argv.index('--app') + 1] == 'odoo-saas-postgres-staging'

    def test_nonzero_exit_returns_restore_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('PGBACKREST_DRY_RUN', raising=False)
        exc = subprocess.CalledProcessError(
            returncode=2, cmd='pgrestore', stderr='pg_restore: error: ...'
        )
        runner = _ScriptedRunner(scripted=[exc])
        result = run(self._pgdump_plan(), subprocess_runner=runner)
        assert result.status == 'restore_failed'
