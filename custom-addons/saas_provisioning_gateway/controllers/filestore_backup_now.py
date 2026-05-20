# Control-plane → source Odoo: synchronous filestore backup trigger.
#
# Phase 3 (moveTier.triggerSourceBackupNow). Before lockSource flips the
# tenant into migrating_to_exclusive, the workflow needs a guarantee
# that the source's most recent filestore_tar in tenant_backups is
# UP-TO-DATE — otherwise rsyncFilestore copies a stale snapshot and
# the target loses any attachments added since the last daily cron.
#
# This endpoint provides that guarantee. It calls
# saas.filestore.backup.run_backup() synchronously and returns when:
#   - the filestore tar has been encrypted + uploaded to S3
#   - the control plane's /api/internal/filestore-backup/complete has
#     inserted the tenant_backups row
#   - OR the upload failed and the addon raised
#
# Auth: identical HMAC envelope to /saas/provision. Same
# SAAS_PROVISIONING_SECRET env var.

import hashlib
import hmac
import json
import logging
import os
import re
import time

import odoo
from odoo import api, http
from odoo.http import request

_logger = logging.getLogger(__name__)

PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'
MAX_DRIFT_SECONDS = 300
DB_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{1,62}$')


class SaasFilestoreBackupNowController(http.Controller):

    @http.route(
        '/saas/internal/filestore-backup-now',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def filestore_backup_now(self, **kwargs):
        secret = os.environ.get(PROVISIONING_SECRET_ENV, '').strip()
        if not secret:
            return self._reject(503, 'provisioning-secret-unset')

        sig = request.httprequest.headers.get('X-SaaS-Signature', '')
        ts_h = request.httprequest.headers.get('X-SaaS-Timestamp', '')
        if not sig or not ts_h:
            return self._reject(401, 'missing-signature-headers')
        try:
            ts = int(ts_h)
        except ValueError:
            return self._reject(401, 'bad-timestamp')
        if abs(time.time() - ts) > MAX_DRIFT_SECONDS:
            return self._reject(410, 'timestamp-drift')

        body = request.httprequest.get_data() or b''
        expected = self._sign(secret, ts_h, body)
        if not hmac.compare_digest(sig, expected):
            return self._reject(401, 'bad-signature')

        try:
            payload = json.loads(body or b'{}')
        except json.JSONDecodeError as exc:
            return self._reject(400, f'bad-json: {exc}')

        db_name = (payload.get('db_name') or '').strip()
        if not DB_NAME_PATTERN.match(db_name):
            return self._reject(400, 'bad-db-name')

        # Spin up a registry for the target tenant DB. We're on the
        # nodb-bound HTTP listener (saas_provisioning_gateway is loaded
        # server-wide), so we can't rely on the per-thread cr being
        # bound to <db_name>. Use Registry(...).cursor() to open one
        # explicitly.
        try:
            registry = odoo.modules.registry.Registry(db_name)
        except Exception as exc:
            _logger.warning(
                'saas_filestore_backup_now: registry load failed db=%s err=%s',
                db_name, exc,
            )
            return self._reject(404, f'db-not-found: {exc}')

        try:
            with registry.cursor() as cr:
                env = api.Environment(cr, odoo.SUPERUSER_ID, {})
                model = env.get('saas.filestore.backup')
                if model is None:
                    return self._reject(500, 'addon-not-installed: saas_filestore_backup')
                # run_backup() returns False when it skipped (no
                # saas.tenant_id, no filestore dir, missing env, etc.),
                # True when the upload + catalog write succeeded.
                result = model.run_backup()
                cr.commit()
        except Exception as exc:
            _logger.exception(
                'saas_filestore_backup_now: run_backup failed db=%s', db_name,
            )
            return self._reject(500, f'run-backup-failed: {str(exc)[:500]}')

        _logger.info(
            'saas_filestore_backup_now: db=%s result=%s', db_name, result,
        )
        return self._ok({
            'db_name': db_name,
            'backed_up': bool(result),
        })

    # ----------- helpers -----------

    def _sign(self, secret, timestamp, body):
        mac = hmac.new(
            secret.encode('utf-8'),
            msg=timestamp.encode('utf-8') + b'.' + body,
            digestmod=hashlib.sha256,
        )
        return 'sha256=' + mac.hexdigest()

    def _ok(self, payload):
        return request.make_json_response({'ok': True, **payload})

    def _reject(self, status, reason):
        _logger.warning(
            'saas_filestore_backup_now reject status=%s reason=%s', status, reason,
        )
        return request.make_json_response({'ok': False, 'error': reason}, status=status)
