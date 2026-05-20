import hashlib
import hmac
import time

from odoo.tests import HttpCase, tagged

TELEMETRY_PATH = '/saas/telemetry'


def _sign(secret, timestamp, body):
    mac = hmac.new(
        secret.encode('utf-8'),
        msg=str(timestamp).encode('utf-8') + b'.' + body,
        digestmod=hashlib.sha256,
    )
    return 'sha256=' + mac.hexdigest()


@tagged('saas_tenant_gate', '-at_install', 'post_install')
class TestTelemetry(HttpCase):

    def setUp(self):
        super().setUp()
        self.secret = 'unit-test-shared-secret-do-not-use-in-prod'
        config = self.env['ir.config_parameter'].sudo()
        config.set_param('saas.telemetry_secret', self.secret)
        config.set_param('saas.tenant_id', 'tenant-test-001')
        config.set_param('saas.plan_code', 'starter')

    def _post(self, body=b'', signature=None, timestamp=None):
        ts = str(timestamp if timestamp is not None else int(time.time()))
        headers = {
            'Content-Type': 'application/json',
            'X-SaaS-Timestamp': ts,
        }
        if signature is None:
            signature = _sign(self.secret, ts, body)
        if signature != '':
            headers['X-SaaS-Signature'] = signature
        # Endpoint is registered with methods=['POST']; pass method explicitly
        # so HttpCase.url_open doesn't fall back to GET when body is b''
        # (empty bytes evaluates falsy in the data-vs-None check).
        return self.url_open(
            TELEMETRY_PATH, data=body, headers=headers, timeout=30, method='POST',
        )

    def test_valid_request_returns_payload(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['tenant_id'], 'tenant-test-001')
        self.assertEqual(payload['plan_code'], 'starter')
        self.assertIn('seat_count', payload)
        self.assertIn('installed_modules', payload)
        self.assertIn('saas_tenant_gate', payload['installed_modules'])
        self.assertEqual(payload['database'], self.env.cr.dbname)

    def test_bad_signature_returns_401(self):
        response = self._post(signature='sha256=' + 'f' * 64)
        self.assertEqual(response.status_code, 401)

    def test_old_timestamp_returns_410(self):
        old_ts = int(time.time()) - 600
        response = self._post(timestamp=old_ts)
        self.assertEqual(response.status_code, 410)

    def test_missing_signature_header_returns_401(self):
        response = self._post(signature='')
        self.assertEqual(response.status_code, 401)

    def test_unconfigured_secret_returns_503(self):
        self.env['ir.config_parameter'].sudo().set_param('saas.telemetry_secret', 'unset')
        response = self._post()
        self.assertEqual(response.status_code, 503)
