# Operator-only endpoint for rotating saas.telemetry_secret post-provision.
#
# Auth contract differs from /saas/telemetry (which uses the per-tenant
# secret itself for auth — useless for rotating it!). This endpoint
# authenticates against SAAS_PROVISIONING_SECRET — the same env-var
# secret used by /saas/provision in the saas_provisioning_gateway addon.
# Both addons share the secret because they're both control-plane-only
# operations that need a pool-level (not per-tenant) credential.
#
# Side effect: ir.config_parameter `saas.telemetry_secret` is overwritten
# with the new value. Control plane MUST persist the new secret on its
# side before calling here, or it'll lose telemetry access until the
# next manual rotation.

import hashlib
import hmac
import json
import logging
import os
import time

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TELEMETRY_SECRET_PARAM = 'saas.telemetry_secret'
PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'
MAX_DRIFT_SECONDS = 300


class SaasTelemetryRotateController(http.Controller):

    @http.route('/saas/rotate-telemetry', type='http', auth='none', methods=['POST'], csrf=False)
    def rotate(self, **kwargs):
        secret = os.environ.get(PROVISIONING_SECRET_ENV, '').strip()
        if not secret:
            return self._reject(503, 'provisioning-secret-unset')

        signature_header = request.httprequest.headers.get('X-SaaS-Signature', '')
        timestamp_header = request.httprequest.headers.get('X-SaaS-Timestamp', '')
        if not signature_header or not timestamp_header:
            return self._reject(401, 'missing-signature-headers')

        try:
            ts = int(timestamp_header)
        except ValueError:
            return self._reject(401, 'bad-timestamp')

        if abs(time.time() - ts) > MAX_DRIFT_SECONDS:
            return self._reject(410, 'timestamp-drift')

        body = request.httprequest.get_data() or b''
        expected = self._sign(secret, timestamp_header, body)
        if not hmac.compare_digest(signature_header, expected):
            return self._reject(401, 'bad-signature')

        try:
            payload = json.loads(body or b'{}')
        except json.JSONDecodeError as exc:
            return self._reject(400, f'bad-json: {exc}')

        new_secret = (payload.get('new_secret') or '').strip()
        if not new_secret or len(new_secret) < 32:
            # 32 hex chars = 16 bytes — bare minimum for HMAC-SHA256 strength.
            # Control plane should send 64 hex (32 bytes) but we'll accept
            # anything >= 32 to keep the door open for custom rotation flows.
            return self._reject(400, 'new-secret-too-short')

        env = request.env(su=True)
        config = env['ir.config_parameter'].sudo()
        previous = config.get_param(TELEMETRY_SECRET_PARAM, '')
        config.set_param(TELEMETRY_SECRET_PARAM, new_secret)
        env.cr.commit()

        _logger.info(
            'saas_tenant_gate.rotate: telemetry secret rotated on db=%s '
            '(prev_len=%d new_len=%d)',
            env.cr.dbname, len(previous), len(new_secret),
        )
        return request.make_json_response({
            'ok': True,
            'database': env.cr.dbname,
            'rotated_at': int(time.time()),
            'previous_was_set': bool(previous and previous != 'unset'),
        })

    def _sign(self, secret, timestamp, body):
        mac = hmac.new(
            secret.encode('utf-8'),
            msg=timestamp.encode('utf-8') + b'.' + body,
            digestmod=hashlib.sha256,
        )
        return 'sha256=' + mac.hexdigest()

    def _reject(self, status, reason):
        _logger.warning('saas_tenant_gate.rotate reject status=%s reason=%s', status, reason)
        return request.make_json_response({'ok': False, 'error': reason}, status=status)
