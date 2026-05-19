"""Filestore backup runner — Phase 2 real flow (HARDENING.md item 5).

Implements Option C from the HARDENING runbook: an Odoo-internal scheduled
action streams the per-tenant filestore directly to S3, encrypted with a
KMS-wrapped DEK issued by the control plane on each run.

Flow on each cron tick:

  1. Resolve saas.tenant_id, saas.filestore_backup_endpoint, and the pool
     SAAS_PROVISIONING_SECRET env var. Skip if any is missing (development
     environment / pre-provisioned tenant).
  2. Tar the filestore dir to a /tmp file. Compute plaintext sha256.
  3. POST to <endpoint>/issue-credentials (HMAC-signed) →
        { s3Key, putUrl, dekHex, kmsCmkArn, expiresAt }.
  4. AES-256-GCM encrypt the tar file → ciphertext file on /tmp.
        Layout: [nonce 12B] [ciphertext N B] [tag 16B] is NOT used — we
        upload only the ciphertext body and pass nonce/tag to /complete
        as headers/metadata so the catalog row carries them in storage_url.
  5. PUT the ciphertext to the presigned URL.
  6. POST /complete with size_bytes, sha256_hex (of ciphertext), nonce/tag,
     plaintext_bytes, kms_cmk_arn → control plane writes the
     tenant_backups row.

Idempotency: each run uses today's date in the S3 key, so re-running the
cron in the same day overwrites that day's object (versioned bucket
keeps history). The complete endpoint inserts a fresh tenant_backups
row each call — retention rotation (HARDENING #4) prunes duplicates.

Failure modes:
  - issue-credentials 5xx / network error → log warning, raise so the
    cron records a failure; tomorrow's tick retries.
  - presigned PUT failure → same.
  - complete 5xx → ciphertext IS on S3 but no catalog row. Audit_log
    on the control plane will eventually surface this; for now we log
    and raise.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import tarfile
import tempfile
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from odoo import api, models

_logger = logging.getLogger(__name__)

_CFG_TENANT_ID = 'saas.tenant_id'
_CFG_BACKUP_ENDPOINT = 'saas.filestore_backup_endpoint'
_PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'

# Chunk size for streaming the tar through sha256 + AES-GCM. Big enough
# to amortize Python's per-call overhead, small enough to bound RAM.
_CHUNK = 1 << 20  # 1 MiB

# Network timeouts — cron windows are bounded; we'd rather fail fast and
# retry than hang for hours on a hung connection.
_HTTP_TIMEOUT = 60

# ----- Streaming AEAD v2 format (lifts the 256 MiB one-shot cap) -----
#
# File layout for v2:
#
#   bytes 0..3   : magic b"GLT2" (so the decoder can dispatch v1 vs v2)
#   bytes 4..15  : base nonce (12 bytes random)
#   bytes 16..19 : chunk size (uint32 big-endian); typical 1 MiB
#   then, repeating until EOF:
#     bytes 0..3 : plaintext chunk length (uint32 big-endian; last chunk
#                  may be smaller than the declared chunk size)
#     N bytes    : AES-256-GCM ciphertext for this chunk
#     16 bytes   : GCM tag for this chunk
#
# Per-chunk nonce: base_nonce[:4] || uint64-big-endian(chunk_index).
# A new counter per chunk guarantees nonce uniqueness within the file's
# DEK lifetime; AES-GCM is safe up to 2^32 messages per key.
#
# v1 (legacy, ≤256 MiB): the file has NO magic prefix, just raw GCM
# ciphertext for the WHOLE plaintext, and the single nonce + tag travel
# out-of-band in the catalog row's storage_url fragment. Restore tooling
# dispatches by reading the first 4 bytes and checking for b"GLT2".

_V2_MAGIC = b'GLT2'
_V2_NONCE_LEN = 12
_V2_TAG_LEN = 16
_V2_CHUNK_LEN_FIELD = 4  # uint32
_V2_DEFAULT_CHUNK = 1 << 20  # 1 MiB plaintext per chunk
_V1_ONESHOT_CAP = 256 * 1024 * 1024


class SaasFilestoreBackup(models.AbstractModel):
    _name = 'saas.filestore.backup'
    _description = 'SaaS — filestore backup runner'

    @api.model
    def run_backup(self):
        """Entry point called by the ir.cron in data/ir_cron_data.xml."""
        secret = (os.environ.get(_PROVISIONING_SECRET_ENV) or '').strip()
        if not secret:
            _logger.info(
                'saas_filestore_backup: %s env var unset — Phase-2 wiring '
                'incomplete, skipping (development environment?)',
                _PROVISIONING_SECRET_ENV,
            )
            return False

        params = self.env['ir.config_parameter'].sudo()
        tenant_id = params.get_param(_CFG_TENANT_ID, '')
        endpoint = params.get_param(_CFG_BACKUP_ENDPOINT, '')

        if not tenant_id or tenant_id == 'unset':
            _logger.info('saas_filestore_backup: saas.tenant_id unset — '
                         'pre-provisioned tenant, skipping')
            return False
        if not endpoint:
            _logger.info('saas_filestore_backup: saas.filestore_backup_endpoint '
                         'not set — skipping (control plane will set this at '
                         'provision time)')
            return False

        db_name = self.env.cr.dbname

        # Odoo 19's ir.attachment._filestore() is the canonical lookup.
        filestore_dir = self.env['ir.attachment']._filestore()  # type: ignore[attr-defined]
        if not filestore_dir or not os.path.isdir(filestore_dir):
            _logger.warning(
                'saas_filestore_backup: filestore directory missing at %r — '
                'nothing to back up (empty tenant?)', filestore_dir,
            )
            return False

        # Step 1: tar to /tmp.
        with tempfile.NamedTemporaryFile(
            prefix=f'saas-filestore-{db_name}-', suffix='.tar', dir='/tmp', delete=False,
        ) as plaintext_fh:
            plaintext_path = plaintext_fh.name
        try:
            self._tar_filestore(filestore_dir, db_name, plaintext_path)
            plaintext_size = os.path.getsize(plaintext_path)
            _logger.info('saas_filestore_backup: tar built db=%s plaintext_bytes=%d',
                         db_name, plaintext_size)

            # Step 2: get credentials from control plane.
            creds = self._issue_credentials(endpoint, secret, db_name)
            dek = bytes.fromhex(creds['dekHex'])
            if len(dek) != 32:
                raise ValueError(f'unexpected DEK length: {len(dek)} (want 32)')

            # Step 3: encrypt to /tmp.
            with tempfile.NamedTemporaryFile(
                prefix=f'saas-filestore-{db_name}-', suffix='.gcm', dir='/tmp', delete=False,
            ) as ct_fh:
                ciphertext_path = ct_fh.name
            try:
                nonce, tag, ciphertext_sha = self._encrypt_file(
                    plaintext_path, ciphertext_path, dek,
                )
                ciphertext_size = os.path.getsize(ciphertext_path)
                _logger.info(
                    'saas_filestore_backup: encrypted db=%s ciphertext_bytes=%d sha256=%s',
                    db_name, ciphertext_size, ciphertext_sha,
                )

                # Step 4: PUT to presigned URL.
                self._put_to_s3(creds['putUrl'], ciphertext_path)

                # Step 5: notify control plane.
                self._complete(
                    endpoint=endpoint,
                    secret=secret,
                    tenant_slug=db_name,
                    s3_key=creds['s3Key'],
                    size_bytes=ciphertext_size,
                    sha256_hex=ciphertext_sha,
                    nonce_hex=nonce.hex(),
                    tag_hex=tag.hex(),
                    plaintext_bytes=plaintext_size,
                    kms_cmk_arn=creds['kmsCmkArn'],
                )
            finally:
                _try_unlink(ciphertext_path)
        finally:
            _try_unlink(plaintext_path)
            # Drop dek reference promptly. Python doesn't zero memory but
            # keeping the binding around longer than needed has no upside.
            try:
                dek = b''  # noqa: F841
            except NameError:
                pass

        return True

    # ------------------------------------------------------------------

    def _tar_filestore(self, filestore_dir, db_name, dest):
        with tarfile.open(dest, mode='w') as tf:
            tf.add(filestore_dir, arcname=db_name)

    def _encrypt_file(self, src_path, dest_path, dek):
        """AES-256-GCM encrypt. Dispatches by size:

        * ≤256 MiB → legacy v1 (raw ciphertext, single nonce+tag returned
          out-of-band). Backward-compatible with old catalog rows.
        * >256 MiB → v2 streaming (b"GLT2" magic + per-chunk GCM,
          self-contained file; out-of-band tag returned EMPTY since
          there are many tags inside the file).

        Returns (nonce, tag, sha256_hex_of_ciphertext_file).

        For v2, `nonce` is the base nonce (informational; the file is
        self-describing via the magic header) and `tag` is empty bytes —
        the restore tool checks the magic header to know which format.
        """
        plaintext_size = os.path.getsize(src_path)
        if plaintext_size <= _V1_ONESHOT_CAP:
            return self._encrypt_file_v1(src_path, dest_path, dek)
        return self._encrypt_file_v2(src_path, dest_path, dek)

    def _encrypt_file_v1(self, src_path, dest_path, dek):
        """Legacy one-shot AES-256-GCM. Cap is 256 MiB plaintext —
        kept for backward-compat so existing catalog rows decrypt as-is
        and tenants below the cap don't pay the streaming overhead.
        """
        with open(src_path, 'rb') as fh:
            plaintext = fh.read()

        nonce = secrets.token_bytes(12)
        aead = AESGCM(dek)
        ciphertext_and_tag = aead.encrypt(nonce, plaintext, None)
        tag = ciphertext_and_tag[-16:]
        ciphertext = ciphertext_and_tag[:-16]

        sha = hashlib.sha256()
        with open(dest_path, 'wb') as fh:
            for i in range(0, len(ciphertext), _CHUNK):
                chunk = ciphertext[i:i + _CHUNK]
                fh.write(chunk)
                sha.update(chunk)
        return nonce, tag, sha.hexdigest()

    def _encrypt_file_v2(self, src_path, dest_path, dek,
                        chunk_size=_V2_DEFAULT_CHUNK):
        """Streaming AES-256-GCM with per-chunk tag + counter-derived
        nonce. No plaintext size cap. File layout documented in the
        module-level _V2_MAGIC comment.

        Returns (base_nonce, b'', sha256_hex_of_ciphertext_file). The
        empty tag is the sentinel for "this row is v2 — read the magic
        in the file to dispatch".
        """
        aead = AESGCM(dek)
        base_nonce = secrets.token_bytes(_V2_NONCE_LEN)
        sha = hashlib.sha256()

        with open(src_path, 'rb') as src, open(dest_path, 'wb') as dst:
            header = _V2_MAGIC + base_nonce + struct.pack('>I', chunk_size)
            dst.write(header)
            sha.update(header)

            chunk_index = 0
            while True:
                pt = src.read(chunk_size)
                if not pt:
                    break  # EOF; file may end on a chunk boundary
                nonce = base_nonce[:4] + struct.pack('>Q', chunk_index)
                ct_and_tag = aead.encrypt(nonce, pt, None)
                # Split ciphertext from tag for explicit framing.
                ct = ct_and_tag[:-_V2_TAG_LEN]
                tag = ct_and_tag[-_V2_TAG_LEN:]
                frame = struct.pack('>I', len(pt)) + ct + tag
                dst.write(frame)
                sha.update(frame)
                chunk_index += 1
                if chunk_index >= (1 << 32):
                    # AES-GCM safe envelope; rotate DEK well before this.
                    raise RuntimeError(
                        'saas_filestore_backup: per-DEK chunk counter exhausted'
                    )

        return base_nonce, b'', sha.hexdigest()

    def _put_to_s3(self, url, src_path):
        size = os.path.getsize(src_path)
        with open(src_path, 'rb') as fh:
            req = urlrequest.Request(
                url,
                data=fh.read(),  # AWS presigned PUTs don't support chunked transfer
                method='PUT',
                headers={
                    'content-type': 'application/octet-stream',
                    'content-length': str(size),
                    # SSE-S3 backstop matches what the presigner included
                    # in the signed request. AWS rejects with 400 otherwise.
                    'x-amz-server-side-encryption': 'AES256',
                },
            )
            try:
                with urlrequest.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    if resp.status >= 300:
                        raise RuntimeError(f'S3 PUT returned HTTP {resp.status}')
            except HTTPError as e:
                body = e.read()[:500].decode('utf-8', 'replace')
                raise RuntimeError(f'S3 PUT failed HTTP {e.code}: {body}') from None
            except URLError as e:
                raise RuntimeError(f'S3 PUT network error: {e.reason}') from None

    def _issue_credentials(self, endpoint, secret, tenant_slug):
        path = endpoint.rstrip('/') + '/issue-credentials'
        return self._signed_post(path, secret, {'tenant_slug': tenant_slug})

    def _complete(self, endpoint, secret, **fields):
        path = endpoint.rstrip('/') + '/complete'
        self._signed_post(path, secret, fields)

    def _signed_post(self, url, secret, body_obj):
        body = json.dumps(body_obj, separators=(',', ':')).encode('utf-8')
        ts = str(int(time.time()))
        sig = 'sha256=' + hmac.new(
            secret.encode('utf-8'), ts.encode('utf-8') + b'.' + body, hashlib.sha256,
        ).hexdigest()
        req = urlrequest.Request(
            url, data=body, method='POST',
            headers={
                'content-type': 'application/json',
                'x-saas-timestamp': ts,
                'x-saas-signature': sig,
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                raw = resp.read()
        except HTTPError as e:
            detail = e.read()[:500].decode('utf-8', 'replace')
            raise RuntimeError(f'{url} HTTP {e.code}: {detail}') from None
        except URLError as e:
            raise RuntimeError(f'{url} network error: {e.reason}') from None
        try:
            payload = json.loads(raw or b'{}')
        except json.JSONDecodeError as err:
            raise RuntimeError(f'{url} returned non-JSON body') from err
        if not payload.get('ok'):
            raise RuntimeError(f'{url} rejected: {payload.get("error")}')
        return payload


def _try_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
