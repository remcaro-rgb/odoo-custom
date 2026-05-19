# Control-plane → target Odoo: restore a tenant's filestore from S3.
#
# Phase 3 (moveTier.rsyncFilestore). After the workflow's restoreToTarget
# step pg_restores the source DB into the per-tenant target cluster,
# this endpoint runs on the TARGET Odoo to repopulate the
# /var/lib/odoo/filestore/<db_name>/ tree from S3.
#
# Why a separate endpoint instead of reusing /saas/provision:
#   - provision builds an EMPTY database via Odoo's _initialize_db helper.
#     The target DB at this point is post-pg_restore — already has tables
#     and ir.attachment rows. The filestore objects those rows point at
#     need to be on disk; without them, attachment fetches 404.
#   - The source's saas_filestore_backup addon already produced an
#     encrypted tar in S3 (daily cron). We just need to decrypt + untar
#     it into the target's filestore volume.
#
# Auth: identical HMAC envelope to /saas/provision. Same
# SAAS_PROVISIONING_SECRET env var.
#
# Request body (JSON, signed):
#   {
#     "db_name":  "<target tenant db name>",
#     "s3_url":   "s3://<warm bucket>/tenants/<id>/filestore/<date>.tar.gcm",
#     "dek_hex":  "<64 hex chars>",
#     "nonce_hex":"<24 hex chars>",
#     "tag_hex":  "<32 hex chars>",
#     "sha256":   "<64 hex chars>",          # optional integrity check
#     "presigned_get_url": "<https url>"     # optional; falls back to
#                                              # AWS_* env on the runner host
#   }
#
# Idempotency: if /var/lib/odoo/filestore/<db_name>/ already has any
# files, the endpoint OVERWRITES (tarfile.extractall semantics). A
# second call with the same artifact is therefore safe but redundant.
#
# Not in scope here:
#   - Pre-flight "is the source backup recent enough?" check. The
#     control plane (moveTier workflow) picks the source filestore_tar
#     row and is responsible for triggering a fresh source backup before
#     calling this endpoint if the latest one is stale.
#   - Streaming AEAD for >256 MiB filestores. AESGCM is one-shot in
#     cryptography==41 (same limit as saas_filestore_backup's encrypt
#     side). Larger filestores need a chunked-AEAD redesign — flagged
#     in the v0.3 plan.

import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'
MAX_DRIFT_SECONDS = 300
DB_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{1,62}$')
S3_URL_PATTERN = re.compile(
    r'^s3://(?P<bucket>[a-z0-9.\-]+)/(?P<key>tenants/[a-f0-9-]+/filestore/\d{4}-\d{2}-\d{2}\.tar\.gcm)$'
)
HEX_64 = re.compile(r'^[0-9a-f]{64}$')
HEX_24 = re.compile(r'^[0-9a-f]{24}$')
HEX_32 = re.compile(r'^[0-9a-f]{32}$')

_HTTP_TIMEOUT = 60
_MAX_PLAINTEXT_BYTES = 256 * 1024 * 1024  # match saas_filestore_backup limit


class SaasFilestoreRestoreController(http.Controller):

    @http.route(
        '/saas/internal/filestore-restore',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def filestore_restore(self, **kwargs):
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

        s3_url = (payload.get('s3_url') or '').strip()
        m = S3_URL_PATTERN.match(s3_url)
        if not m:
            return self._reject(400, 'bad-s3-url')

        dek_hex = (payload.get('dek_hex') or '').strip()
        nonce_hex = (payload.get('nonce_hex') or '').strip()
        tag_hex = (payload.get('tag_hex') or '').strip()
        if not (HEX_64.match(dek_hex) and HEX_24.match(nonce_hex) and HEX_32.match(tag_hex)):
            return self._reject(400, 'bad-crypto-params')

        expected_sha256 = payload.get('sha256')
        if expected_sha256 is not None and not HEX_64.match(expected_sha256):
            return self._reject(400, 'bad-sha256')

        presigned_get_url = payload.get('presigned_get_url') or None

        dek = bytes.fromhex(dek_hex)
        nonce = bytes.fromhex(nonce_hex)
        tag = bytes.fromhex(tag_hex)

        # Resolve filestore directory. ir.attachment._filestore() returns
        # the per-db location — but at this point Odoo's registry for db_name
        # may not be loaded into THIS worker yet (we got here on the
        # nodb-bound HTTP listener). Bypass the registry and compute it
        # the same way Odoo does: <data_dir>/filestore/<db_name>.
        from odoo.tools import config as odoo_config
        data_dir = odoo_config.get('data_dir')
        filestore_dir = os.path.join(data_dir, 'filestore', db_name)

        with tempfile.NamedTemporaryFile(
            prefix='saas-filestore-restore-', suffix='.gcm',
            dir='/tmp', delete=False,
        ) as ct_fh:
            ct_path = ct_fh.name
        try:
            self._download(s3_url, presigned_get_url, ct_path)
            if expected_sha256:
                actual = self._sha256_file(ct_path)
                if actual != expected_sha256:
                    return self._reject(
                        422, f'sha256-mismatch got={actual} expected={expected_sha256}',
                    )

            tar_path = ct_path + '.tar'
            try:
                self._decrypt(ct_path, tar_path, dek, nonce, tag)

                # Source-side tar was built with arcname=<source_db_name>.
                # After pg_restore the target's ir.attachment rows reference
                # paths derived from the SOURCE db_name (Odoo uses content
                # hash subdirectories, not the db_name, BUT the root path
                # uses db_name). For a same-name migration this is trivial.
                # For a rename migration: extract to a temp dir, then
                # move/rename the inner directory to db_name.
                tmp_extract = tempfile.mkdtemp(prefix='saas-filestore-extract-', dir='/tmp')
                try:
                    with tarfile.open(tar_path, mode='r') as tf:
                        # `filter` arg is required on Python 3.12+ for
                        # CVE-2007-4559 mitigations. 'data' is the safest
                        # filter — strips suid/sgid bits and refuses
                        # absolute/escape paths.
                        tf.extractall(path=tmp_extract, filter='data')
                    self._install_filestore(tmp_extract, db_name, filestore_dir)
                finally:
                    shutil.rmtree(tmp_extract, ignore_errors=True)
            finally:
                _try_unlink(tar_path)
        finally:
            _try_unlink(ct_path)

        _logger.info(
            'saas_filestore_restore: restored db=%s from %s', db_name, s3_url,
        )
        return self._ok({'db_name': db_name, 'restored': True, 's3_url': s3_url})

    # ---------- helpers ----------

    def _sign(self, secret, timestamp, body):
        mac = hmac.new(
            secret.encode('utf-8'),
            msg=timestamp.encode('utf-8') + b'.' + body,
            digestmod=hashlib.sha256,
        )
        return 'sha256=' + mac.hexdigest()

    def _download(self, s3_url, presigned_get_url, dest_path):
        if presigned_get_url:
            url = presigned_get_url
        else:
            # Fall back to AWS_* env on the running Odoo container. Most
            # production deploys won't have AWS creds inside Odoo; the
            # control plane should always send presigned_get_url. Kept as
            # a development fallback.
            raise RuntimeError(
                'filestore-restore: presigned_get_url required (no AWS SDK in Odoo container)'
            )
        req = urlrequest.Request(url, method='GET')
        try:
            with urlrequest.urlopen(req, timeout=_HTTP_TIMEOUT) as resp, open(dest_path, 'wb') as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
        except HTTPError as e:
            detail = e.read()[:500].decode('utf-8', 'replace')
            raise RuntimeError(
                f'filestore-restore: S3 GET {s3_url} failed HTTP {e.code}: {detail}'
            ) from e
        except URLError as e:
            raise RuntimeError(
                f'filestore-restore: S3 GET network error: {e.reason}'
            ) from e

    def _decrypt(self, ct_path, pt_path, dek, nonce, tag):
        size = os.path.getsize(ct_path)
        if size > _MAX_PLAINTEXT_BYTES:
            raise RuntimeError(
                'filestore-restore: ciphertext > 256 MiB; switch to streaming AEAD'
            )
        with open(ct_path, 'rb') as fh:
            ct = fh.read()
        # AESGCM.decrypt expects ciphertext concatenated with tag.
        plaintext = AESGCM(dek).decrypt(nonce, ct + tag, None)
        with open(pt_path, 'wb') as fh:
            fh.write(plaintext)

    def _install_filestore(self, extract_root, db_name, target_dir):
        # The source-side tar was built with `arcname=<source_db_name>` so
        # extract_root now contains a single subdirectory named after the
        # source DB. For Phase 3.0 (no rename support), source_db_name ==
        # target_db_name, so the subdir matches db_name exactly. Move it
        # into place atomically.
        children = os.listdir(extract_root)
        if len(children) != 1:
            raise RuntimeError(
                f'filestore-restore: expected exactly 1 dir in tar, got {children}'
            )
        inner = os.path.join(extract_root, children[0])
        if not os.path.isdir(inner):
            raise RuntimeError(
                f'filestore-restore: tar root {inner} is not a directory'
            )

        # Target dir may exist (re-run of moveTier). Move it aside so we
        # always end up with a clean tree from the source's snapshot.
        if os.path.exists(target_dir):
            staged = '%s.old.%d' % (target_dir, int(time.time()))
            os.rename(target_dir, staged)
            _logger.warning(
                'saas_filestore_restore: existing filestore moved to %s', staged,
            )
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        shutil.move(inner, target_dir)

    def _sha256_file(self, path):
        h = hashlib.sha256()
        with open(path, 'rb') as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _ok(self, payload):
        return request.make_json_response({'ok': True, **payload})

    def _reject(self, status, reason):
        _logger.warning(
            'saas_filestore_restore reject status=%s reason=%s', status, reason,
        )
        return request.make_json_response({'ok': False, 'error': reason}, status=status)


def _try_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
