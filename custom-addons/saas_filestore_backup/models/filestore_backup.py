# -*- coding: utf-8 -*-
"""Filestore-backup model — exposes one method the ir.cron entry calls.

Phase 1 (this commit) ships the skeleton: the cron triggers, the method
resolves the per-tenant config parameters, locates the filestore on disk,
and logs what it WOULD do. Phase 2 wires the real S3 + control-plane
endpoints.

The reason for shipping the skeleton now even with stub bodies: it gets the
cron entry into the ir.cron table on every NEW tenant DB (via auto_install),
so when Phase-2 code lands, a single ``-u saas_filestore_backup`` upgrade
on existing tenants picks up the real logic. No new cron-registration pass
needed.
"""

import hashlib
import hmac
import json
import logging
import os
import tarfile
import tempfile
import time
from urllib import request as urlrequest

from odoo import api, models

_logger = logging.getLogger(__name__)

# Optional ir.config_parameter keys consumed by run_backup. None of these
# need to be set for the cron to be safely a no-op — that's the
# "development environment" path.
_CFG_TENANT_ID = 'saas.tenant_id'
_CFG_TELEMETRY_SECRET = 'saas.telemetry_secret'
_CFG_BACKUP_ENDPOINT = 'saas.filestore_backup_endpoint'


class SaasFilestoreBackup(models.AbstractModel):
    _name = 'saas.filestore.backup'
    _description = 'SaaS — filestore backup runner'

    @api.model
    def run_backup(self):
        """Entry point called by the ir.cron registered in data/ir_cron_data.xml.

        Returns silently on any "configuration not set" path so the cron
        doesn't spam the log during development; raises only on real
        failures (S3 5xx, disk full, etc.).
        """
        params = self.env['ir.config_parameter'].sudo()
        tenant_id = params.get_param(_CFG_TENANT_ID, '')
        telemetry_secret = params.get_param(_CFG_TELEMETRY_SECRET, '')
        endpoint = params.get_param(_CFG_BACKUP_ENDPOINT, '')

        if not tenant_id or tenant_id == 'unset':
            _logger.info('saas_filestore_backup: saas.tenant_id is unset — '
                         'control plane has not finished provisioning yet, skipping')
            return False
        if not telemetry_secret or telemetry_secret == 'unset':
            _logger.info('saas_filestore_backup: saas.telemetry_secret unset — skipping')
            return False
        if not endpoint:
            _logger.info('saas_filestore_backup: saas.filestore_backup_endpoint not set — '
                         'Phase-2 control-plane wiring deferred, skipping')
            return False

        db_name = self.env.cr.dbname
        # data_dir/filestore/<db_name> is Odoo's canonical filestore path
        filestore_dir = self.env['ir.attachment']._filestore()  # type: ignore[attr-defined]
        if not filestore_dir or not os.path.isdir(filestore_dir):
            _logger.warning('saas_filestore_backup: filestore directory missing at %r — '
                            'nothing to back up', filestore_dir)
            return False

        # Streaming tar to a temp file. We bound to /tmp so the addon
        # doesn't accidentally fill the data volume.
        with tempfile.NamedTemporaryFile(
            prefix=f'saas-filestore-{db_name}-',
            suffix='.tar',
            dir='/tmp',
            delete=False,
        ) as tmp:
            try:
                with tarfile.open(tmp.name, mode='w') as tf:
                    tf.add(filestore_dir, arcname=db_name)
                size = os.path.getsize(tmp.name)
                sha256 = _sha256_of_file(tmp.name)
                _logger.info('saas_filestore_backup: tar built db=%s size=%d sha256=%s',
                             db_name, size, sha256)

                # Phase 2: fetch DEK + presigned URL from control plane
                # (HMAC-signed GET); AES-256-GCM encrypt; PUT to S3; POST
                # metadata back. For Phase 1, log + delete.
                _logger.info(
                    'saas_filestore_backup: TODO Phase 2 — encrypt + upload to %s '
                    '(tenant_id=%s, size=%d, sha256=%s)',
                    endpoint, tenant_id, size, sha256,
                )
                # Best-effort liveness ping so the control plane knows the
                # cron is alive even before Phase 2 lands. HMAC-signs the
                # ping body so a forged request can't write an audit entry.
                _post_liveness_ping(endpoint, telemetry_secret, tenant_id, db_name, size, sha256)
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

        return True


def _sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _post_liveness_ping(endpoint, secret, tenant_id, db_name, size, sha256):
    """Best-effort POST to the control plane saying "this cron ran".

    Times out fast; never raises (we don't want a control-plane outage to
    block the backup from rolling over). HMAC-SHA256 over
    timestamp + '.' + body so the control plane can verify it came from
    this tenant.
    """
    body = json.dumps({
        'event': 'filestore_backup.tick',
        'tenant_id': tenant_id,
        'db_name': db_name,
        'size': size,
        'sha256': sha256,
    }).encode('utf-8')
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode('utf-8'), (ts + '.').encode('utf-8') + body,
                   hashlib.sha256).hexdigest()
    req = urlrequest.Request(
        endpoint,
        data=body,
        method='POST',
        headers={
            'content-type': 'application/json',
            'x-saas-tenant-id': tenant_id,
            'x-saas-timestamp': ts,
            'x-saas-signature': 'sha256=' + sig,
        },
    )
    try:
        urlrequest.urlopen(req, timeout=5)
    except Exception as e:
        _logger.warning('saas_filestore_backup: liveness ping failed (non-fatal): %s', e)
