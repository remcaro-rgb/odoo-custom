"""Unit tests for migration_runner.snapshot — specifically the
``_parse_backup_label`` parser which decodes pgbackrest stdout, the
``_parse_snapshot_key`` parser for pgdump output, and the
``_snapshot_via_pgdump`` SSH wrapper invocation.

Originally added during Tier 5 Item 3 validation when pgbackrest 2.50+
"new backup label" format wasn't recognized; extended for Tier 5
Item 2 (per-tenant pgdump path)."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from migration_runner.snapshot import (
    SnapshotError,
    _parse_backup_label,
    _parse_snapshot_key,
    _snapshot_via_pgdump,
)


class TestParseBackupLabelNewFormat:
    """pgbackrest 2.50+ format: 'INFO: new backup label = <label>'."""

    def test_parses_incremental_label_from_real_257_output(self) -> None:
        # Real stdout captured from the migration-runner daemon on
        # 2026-05-27 during the Tier 5 Item 3 drill against acmesas2.
        stdout = (
            '2026-05-27 06:53:22.191 P00   INFO: last backup label = '
            '20260524-065900F_20260526-065247D, version = 2.57.0\n'
            '2026-05-27 06:53:22.191 P00   INFO: execute non-exclusive backup start\n'
            '2026-05-27 06:53:24.639 P00   INFO: '
            'new backup label = 20260524-065900F_20260527-065322I\n'
            '2026-05-27 06:53:25.504 P00   INFO: incr backup size = 2.5MB\n'
        )
        assert _parse_backup_label(stdout) == '20260524-065900F_20260527-065322I'

    def test_parses_full_backup_label(self) -> None:
        stdout = '2026-05-27 INFO: new backup label = 20260527-120000F\n'
        assert _parse_backup_label(stdout) == '20260527-120000F'


class TestParseBackupLabelLegacyFormat:
    """pre-2.50 format: 'INFO: <type> backup: label = <label>' — kept
    so we can re-deploy older Postgres images without breaking the
    parser."""

    def test_parses_legacy_full_backup_format(self) -> None:
        stdout = 'INFO: full backup: label = 20260523-220000F\n'
        assert _parse_backup_label(stdout) == '20260523-220000F'

    def test_parses_legacy_incr_backup_format(self) -> None:
        stdout = 'INFO: incr backup: label = 20260523-220000F_20260524-100000I\n'
        assert _parse_backup_label(stdout) == '20260523-220000F_20260524-100000I'


class TestParseBackupLabelSelectivity:
    """The parser must NOT return the 'last backup label' line — that's
    the prior backup, not this run's. Returning it would write a stale
    snapshot_id that rollback's `pgbackrest info` lookup wouldn't
    associate with the just-completed job."""

    def test_prefers_new_over_last_when_both_present(self) -> None:
        stdout = (
            'INFO: last backup label = OLD-LABEL\n'
            'INFO: new backup label = NEW-LABEL\n'
        )
        assert _parse_backup_label(stdout) == 'NEW-LABEL'

    def test_returns_none_when_only_last_present(self) -> None:
        # 'last backup label = ...' alone (no 'new' line) means the
        # backup didn't actually run — never claim it as ours.
        # The current parser intentionally matches only 'new backup
        # label = ' and 'backup: label = ', not 'last backup label = '.
        stdout = 'INFO: last backup label = SOMEONE-ELSES-LABEL\n'
        assert _parse_backup_label(stdout) is None


class TestParseBackupLabelEmptyOrMissing:
    def test_returns_none_on_empty_stdout(self) -> None:
        assert _parse_backup_label('') is None

    def test_returns_none_when_no_label_line(self) -> None:
        stdout = 'INFO: backup command begin\nINFO: backup command end\n'
        assert _parse_backup_label(stdout) is None


class TestParseSnapshotKey:
    """pgdump-snapshot.sh prints SNAPSHOT_KEY=<key> on its last line."""

    def test_parses_well_formed_key(self) -> None:
        stdout = (
            'upload: ./- to s3://goliatt-odoo-saas-hot/pgdump/acmesas2/20260527T120000Z.dump\n'
            'SNAPSHOT_KEY=pgdump/acmesas2/20260527T120000Z.dump\n'
        )
        assert _parse_snapshot_key(stdout) == 'pgdump/acmesas2/20260527T120000Z.dump'

    def test_returns_none_when_missing(self) -> None:
        stdout = 'aws: command not found\n'
        assert _parse_snapshot_key(stdout) is None

    def test_returns_none_on_empty(self) -> None:
        assert _parse_snapshot_key('') is None


class TestSnapshotViaPgdump:
    """SSH-invocation argv shape + output parsing."""

    def test_invokes_pgdump_wrapper_with_db_and_slug(self) -> None:
        ok = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='SNAPSHOT_KEY=pgdump/acmesas2/20260527T120000Z.dump\n',
            stderr='',
        )
        with patch('migration_runner.snapshot.subprocess.run', return_value=ok) as mock_run:
            key = _snapshot_via_pgdump(tenant_slug='acmesas2', db_name='acmesas2')
        assert key == 'pgdump/acmesas2/20260527T120000Z.dump'
        # Argv must SSH-delegate to odoo-saas-postgres + call the wrapper.
        argv = mock_run.call_args.args[0]
        assert argv[0] == 'flyctl'
        assert argv[1:5] == ['ssh', 'console', '--app', 'odoo-saas-postgres']
        assert argv[5] == '--command'
        assert argv[6] == '/usr/local/bin/pgdump-snapshot.sh acmesas2 acmesas2'

    def test_uses_PGBACKREST_SSH_APP_override(self, monkeypatch) -> None:
        monkeypatch.setenv('PGBACKREST_SSH_APP', 'odoo-saas-postgres-staging')
        ok = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='SNAPSHOT_KEY=pgdump/x/y.dump\n', stderr='',
        )
        with patch('migration_runner.snapshot.subprocess.run', return_value=ok) as mock_run:
            _snapshot_via_pgdump(tenant_slug='x', db_name='x')
        argv = mock_run.call_args.args[0]
        assert '--app' in argv
        assert argv[argv.index('--app') + 1] == 'odoo-saas-postgres-staging'

    def test_raises_on_missing_snapshot_key_line(self) -> None:
        # Wrapper failed silently — no SNAPSHOT_KEY line. Treat as error.
        ok = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='some random output\n', stderr='',
        )
        with patch('migration_runner.snapshot.subprocess.run', return_value=ok):
            with pytest.raises(SnapshotError, match='pgdump produced no SNAPSHOT_KEY'):
                _snapshot_via_pgdump(tenant_slug='x', db_name='x')

    def test_raises_on_nonzero_exit(self) -> None:
        exc = subprocess.CalledProcessError(
            returncode=2, cmd=[], output='', stderr='aws: NoSuchBucket'
        )
        with patch('migration_runner.snapshot.subprocess.run', side_effect=exc):
            with pytest.raises(SnapshotError, match='pgdump-snapshot exit 2'):
                _snapshot_via_pgdump(tenant_slug='x', db_name='x')

    def test_raises_on_flyctl_missing(self) -> None:
        with patch(
            'migration_runner.snapshot.subprocess.run',
            side_effect=FileNotFoundError('flyctl'),
        ):
            with pytest.raises(SnapshotError, match='flyctl not on PATH'):
                _snapshot_via_pgdump(tenant_slug='x', db_name='x')
