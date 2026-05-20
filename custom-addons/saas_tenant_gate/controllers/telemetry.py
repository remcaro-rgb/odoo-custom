import hashlib
import hmac
import logging
import time

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TELEMETRY_SECRET_PARAM = 'saas.telemetry_secret'
TENANT_ID_PARAM = 'saas.tenant_id'
PLAN_CODE_PARAM = 'saas.plan_code'

# Maximum drift between the client's signed timestamp and our wall clock.
# Replay protection. Five minutes mirrors the WAL RPO; clock skew between the
# control plane and tenant Odoo should never exceed this in practice.
TELEMETRY_MAX_DRIFT_SECONDS = 300


class SaasTelemetryController(http.Controller):

    @http.route('/saas/telemetry', type='http', auth='none', methods=['POST'], csrf=False)
    def telemetry(self, **kwargs):
        env = request.env(su=True)
        config = env['ir.config_parameter'].sudo()

        secret = config.get_param(TELEMETRY_SECRET_PARAM, '')
        if not secret or secret == 'unset':
            return self._reject(503, 'telemetry-secret-unset')

        signature_header = request.httprequest.headers.get('X-SaaS-Signature', '')
        timestamp_header = request.httprequest.headers.get('X-SaaS-Timestamp', '')
        if not signature_header or not timestamp_header:
            return self._reject(401, 'missing-signature-headers')

        try:
            ts = int(timestamp_header)
        except ValueError:
            return self._reject(401, 'bad-timestamp')

        if abs(time.time() - ts) > TELEMETRY_MAX_DRIFT_SECONDS:
            return self._reject(410, 'timestamp-drift')

        body = request.httprequest.get_data() or b''
        expected = self._sign(secret, timestamp_header, body)
        if not hmac.compare_digest(signature_header, expected):
            return self._reject(401, 'bad-signature')

        payload = self._collect_telemetry(env)
        return request.make_json_response(payload)

    def _sign(self, secret, timestamp, body):
        mac = hmac.new(
            secret.encode('utf-8'),
            msg=timestamp.encode('utf-8') + b'.' + body,
            digestmod=hashlib.sha256,
        )
        return 'sha256=' + mac.hexdigest()

    def _collect_telemetry(self, env):
        config = env['ir.config_parameter'].sudo()
        seat_count = env['res.users'].sudo().search_count([
            ('share', '=', False),
            ('active', '=', True),
        ])
        installed = env['ir.module.module'].sudo().search([('state', '=', 'installed')])
        return {
            'tenant_id': config.get_param(TENANT_ID_PARAM, 'unset'),
            'plan_code': config.get_param(PLAN_CODE_PARAM, 'unset'),
            'database': env.cr.dbname,
            'seat_count': seat_count,
            'installed_modules': sorted(installed.mapped('name')),
            'observed_at': int(time.time()),
        }

    def _reject(self, status, reason):
        _logger.warning('saas_tenant_gate.telemetry reject status=%s reason=%s', status, reason)
        return request.make_json_response({'error': reason}, status=status)
