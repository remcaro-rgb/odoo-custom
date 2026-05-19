# Control-plane → Odoo pool provisioning endpoint.
#
# Replaces the workflow's POST to ``/web/database/create``, which is hard-
# gated by ``list_db = False`` in production via the
# ``@check_db_management_enabled`` decorator on
# ``odoo.service.db.exp_create_database`` (raises AccessDenied before
# touching the master password or the dbfilter). We call the underlying
# helpers (``_create_empty_database`` + ``_initialize_db``) directly to
# bypass that decorator while staying inside Odoo's own create flow.
#
# Auth: HMAC-SHA256 over ``timestamp.body`` using the
# SAAS_PROVISIONING_SECRET env var. Mirrors the existing telemetry HMAC
# pattern in ``saas_tenant_gate`` so the control plane has a single
# signing recipe.
#
# Idempotency: re-POST with the same db_name returns 200 + ok=true if the
# DB already exists. Matches the workflow's createTenantDatabase step
# which already treats "already exists" as a success path.

import hashlib
import hmac
import json
import logging
import os
import re
import time

import odoo
import odoo.sql_db
from odoo import http
from odoo.http import request
from odoo.service.db import _create_empty_database, _initialize_db

_logger = logging.getLogger(__name__)

PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'
MAX_DRIFT_SECONDS = 300
DB_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{1,62}$')


class SaasProvisioningController(http.Controller):

    @http.route(
        '/saas/provision',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def provision(self, **kwargs):
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

        db_name = (payload.get('db_name') or '').strip()
        if not DB_NAME_PATTERN.match(db_name):
            return self._reject(400, 'bad-db-name')

        admin_password = payload.get('admin_password') or ''
        if not admin_password or len(admin_password) < 8:
            return self._reject(400, 'admin-password-too-short')

        admin_login = payload.get('admin_login') or 'admin'
        lang = payload.get('lang') or 'en_US'
        country_code = payload.get('country_code') or None
        phone = payload.get('phone') or None
        demo = bool(payload.get('demo', False))

        # Idempotency: if a DB with this name already exists, return ok=true.
        # The workflow treats "already exists" as a success path for crash-
        # resume scenarios where _create_empty_database completed but the
        # follow-up steps didn't.
        if self._db_exists(db_name):
            _logger.info(
                'saas_provisioning_gateway.provision: db=%s already exists; '
                'returning idempotent success', db_name,
            )
            return self._ok({'db_name': db_name, 'created': False, 'already_existed': True})

        try:
            _create_empty_database(db_name)
            _initialize_db(
                db_name,
                demo,
                lang,
                admin_password,
                admin_login,
                country_code,
                phone,
            )
        except Exception as exc:
            _logger.exception(
                'saas_provisioning_gateway.provision: create failed db=%s', db_name,
            )
            # Best-effort cleanup so the next retry isn't blocked by a
            # half-built DB. _create_empty_database is what populated
            # pg_database; the registry isn't loaded yet so we drop the
            # raw DB directly via the postgres connection.
            self._drop_db_quietly(db_name)
            return self._reject(500, 'create-failed: %s' % (str(exc) or repr(exc)))

        _logger.info(
            'saas_provisioning_gateway.provision: created db=%s lang=%s login=%s',
            db_name, lang, admin_login,
        )
        return self._ok({'db_name': db_name, 'created': True, 'already_existed': False})

    # ----------- helpers -----------

    def _sign(self, secret, timestamp, body):
        mac = hmac.new(
            secret.encode('utf-8'),
            msg=timestamp.encode('utf-8') + b'.' + body,
            digestmod=hashlib.sha256,
        )
        return 'sha256=' + mac.hexdigest()

    def _db_exists(self, db_name):
        try:
            # Use the same helper Odoo uses internally — checks pg_database
            # via the postgres connection without requiring the registry to
            # be loaded.
            return odoo.service.db.exp_db_exist(db_name)
        except Exception:
            _logger.exception('saas_provisioning_gateway: db_exist probe failed')
            return False

    def _drop_db_quietly(self, db_name):
        try:
            db = odoo.sql_db.db_connect('postgres')
            with db.cursor() as cr:
                cr._cnx.autocommit = True
                cr.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        except Exception:
            _logger.exception(
                'saas_provisioning_gateway: cleanup DROP DATABASE failed for %s; '
                'manual cleanup required', db_name,
            )

    def _ok(self, payload):
        return request.make_json_response({'ok': True, **payload})

    def _reject(self, status, reason):
        _logger.warning(
            'saas_provisioning_gateway.provision reject status=%s reason=%s', status, reason,
        )
        return request.make_json_response({'ok': False, 'error': reason}, status=status)
