"""License gate — runtime verdict + enforcement hooks.

Lifecycle
---------

1. Hourly ir.cron calls SaasLicenseGate.run_check(). That:
   - Builds the HMAC envelope from SAAS_PROVISIONING_SECRET.
   - POSTs to {LICENSE_AUTHORITY_URL}/api/internal/license/check with
     {license_id, image_sha256, machine_id, timestamp}.
   - Verifies the Ed25519 signature on the response against the
     embedded /etc/saas-license-pubkey.pem.
   - Persists the verdict to ir.config_parameter (saas.license.status,
     saas.license.checked_at, saas.license.payload).

2. Two helper class-methods, currently_valid() and currently_in_grace(),
   read the cached verdict synchronously without making a network
   call. These are what the enforcement decorators (next: applied to
   account.move, sale.order, etc.) call to decide whether to allow a
   write.

3. If the cached verdict is older than _STALE_THRESHOLD_SECONDS (14
   days) the gate refuses all writes — protects against an attacker
   blocking network access to indefinitely freeze a "last good"
   verdict.

Threat model
-----------

This addon is NOT trying to be unbreakable DRM. It's a license
*enforcement* layer for legitimate enterprise customers who agree to
the EULA. Attackers with code modification rights can always patch
the addon out. What it does prevent:

  - A customer running the image past expires_at without renewing.
  - A customer running an OLD image after their license is revoked
    (the cron will fail the signature on the next tick).
  - A customer running an image they didn't license at all (the
    pre_init_hook in hooks.py refuses to install without LICENSE_ID).

What it doesn't prevent:

  - A customer who patches saas_license_gate out of the image.
  - A customer who runs a totally different (unlicensed) Odoo build.
    For those scenarios our remedy is contractual (EULA + audit
    rights), not cryptographic.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from odoo import api, models

_logger = logging.getLogger(__name__)

# Config-parameter keys — written by run_check, read by everyone else.
_CFG_STATUS = 'saas.license.status'
_CFG_CHECKED_AT = 'saas.license.checked_at'  # unix seconds
_CFG_PAYLOAD = 'saas.license.payload'  # canonical-JSON of last good payload
_CFG_MACHINE_ID = 'saas.license.machine_id'  # generated on first boot if not in env

# Env vars (read at runtime, not import — easier to test).
_LICENSE_ID_ENV = 'LICENSE_ID'
_AUTHORITY_URL_ENV = 'LICENSE_AUTHORITY_URL'
_PROVISIONING_SECRET_ENV = 'SAAS_PROVISIONING_SECRET'
_IMAGE_DIGEST_ENV = 'ODOO_IMAGE_DIGEST'

_PUBKEY_PATH = '/etc/saas-license-pubkey.pem'
_HTTP_TIMEOUT = 30
_STALE_THRESHOLD_SECONDS = 14 * 86400  # 14 days

# Statuses we recognize on the wire (from the control plane's
# evaluateLicense() return value).
_STATUS_ACTIVE = 'active'
_STATUS_GRACE = 'grace'
_STATUS_EXPIRED = 'expired'
_STATUS_REVOKED = 'revoked'
_STATUS_IMAGE_MISMATCH = 'image-mismatch'
_STATUS_NETWORK_FAILED = 'network-failed'  # purely local — never returned by authority
_STATUS_BAD_SIGNATURE = 'bad-signature'  # purely local — never returned by authority
_STATUS_STALE = 'stale'  # purely local — set when cached verdict is too old


class SaasLicenseGate(models.AbstractModel):
    _name = 'saas.license.gate'
    _description = 'SaaS — enterprise self-host license gate'

    # ------------------------------------------------------------------
    # Cron entry point
    # ------------------------------------------------------------------

    @api.model
    def run_check(self):
        """Called by data/ir_cron_data.xml on every cron tick."""
        license_id = (os.environ.get(_LICENSE_ID_ENV) or '').strip()
        authority = (os.environ.get(_AUTHORITY_URL_ENV) or '').strip().rstrip('/')
        secret = (os.environ.get(_PROVISIONING_SECRET_ENV) or '').strip()
        image_digest = (os.environ.get(_IMAGE_DIGEST_ENV) or '').strip().lower()
        if not (license_id and authority and secret and image_digest):
            _logger.warning(
                'saas_license_gate: missing required env vars; cron tick noop '
                '(license_id_set=%s authority_set=%s secret_set=%s digest_set=%s)',
                bool(license_id), bool(authority), bool(secret), bool(image_digest),
            )
            return False

        machine_id = self._get_or_create_machine_id()
        ts = int(time.time())
        body = json.dumps({
            'license_id': license_id,
            'image_sha256': image_digest,
            'machine_id': machine_id,
            'timestamp': ts,
        }, separators=(',', ':'), sort_keys=True).encode('utf-8')

        signature_hdr = 'sha256=' + hmac.new(
            secret.encode('utf-8'),
            f'{ts}.'.encode() + body,
            hashlib.sha256,
        ).hexdigest()

        url = f'{authority}/api/internal/license/check'
        req = urlrequest.Request(
            url,
            data=body,
            method='POST',
            headers={
                'content-type': 'application/json',
                'x-saas-signature': signature_hdr,
                'x-saas-timestamp': str(ts),
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                raw = resp.read()
        except HTTPError as e:
            err_body = ''
            try:
                err_body = e.read().decode('utf-8', errors='replace')[:500]
            except Exception:
                pass
            _logger.warning(
                'saas_license_gate: authority returned HTTP %s: %s',
                e.code, err_body,
            )
            self._record_failure(_STATUS_NETWORK_FAILED, ts)
            return False
        except URLError as e:
            _logger.warning('saas_license_gate: network failure: %s', e)
            self._record_failure(_STATUS_NETWORK_FAILED, ts)
            return False

        try:
            envelope = json.loads(raw)
            payload_str = envelope['payload']
            signature_hex = envelope['signature']
        except (KeyError, TypeError, ValueError) as e:
            _logger.error('saas_license_gate: malformed authority response: %s', e)
            self._record_failure(_STATUS_BAD_SIGNATURE, ts)
            return False

        if not self._verify_signature(payload_str, signature_hex):
            _logger.error('saas_license_gate: SIGNATURE VERIFICATION FAILED')
            self._record_failure(_STATUS_BAD_SIGNATURE, ts)
            return False

        try:
            payload = json.loads(payload_str)
        except ValueError as e:
            _logger.error('saas_license_gate: payload not JSON: %s', e)
            self._record_failure(_STATUS_BAD_SIGNATURE, ts)
            return False

        # Defensive: the payload must echo our license_id + machine_id
        # back. Otherwise an attacker could replay a known-good payload
        # for a different license.
        if payload.get('license_id') != license_id:
            _logger.error(
                'saas_license_gate: payload license_id mismatch (got %s, expected %s)',
                payload.get('license_id'), license_id,
            )
            self._record_failure(_STATUS_BAD_SIGNATURE, ts)
            return False
        if payload.get('machine_id') != machine_id:
            _logger.error('saas_license_gate: payload machine_id mismatch')
            self._record_failure(_STATUS_BAD_SIGNATURE, ts)
            return False
        if payload.get('image_sha256', '').lower() != image_digest:
            # The authority told us image-mismatch; mirror that.
            pass  # status itself will reflect it

        status = payload.get('status', _STATUS_BAD_SIGNATURE)
        self._record_success(status, ts, payload_str)
        _logger.info(
            'saas_license_gate: check OK status=%s expires=%s',
            status, payload.get('expires_at'),
        )
        return True

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _record_failure(self, status, ts):
        """Network/sig failure: don't overwrite the last-good payload, but
        bump status + checked_at so callers see the freshness."""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(_CFG_STATUS, status)
        ICP.set_param(_CFG_CHECKED_AT, str(ts))
        # Leave _CFG_PAYLOAD untouched so currently_valid() can still
        # consult the previous verdict during transient outages.

    def _record_success(self, status, ts, payload_str):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(_CFG_STATUS, status)
        ICP.set_param(_CFG_CHECKED_AT, str(ts))
        ICP.set_param(_CFG_PAYLOAD, payload_str)

    def _get_or_create_machine_id(self):
        """Pin a stable per-database machine identifier. Read /etc/machine-id
        if present (Linux systemd-init guarantees uniqueness per host);
        otherwise generate a UUID4 and persist it. Treated as opaque
        on the wire — the authority only logs it for audit."""
        ICP = self.env['ir.config_parameter'].sudo()
        existing = ICP.get_param(_CFG_MACHINE_ID)
        if existing:
            return existing
        # Try /etc/machine-id first.
        candidate = ''
        try:
            with open('/etc/machine-id', encoding='utf-8') as f:
                candidate = f.read().strip()
        except (OSError, ValueError):
            candidate = ''
        if not candidate:
            candidate = uuid.uuid4().hex
        ICP.set_param(_CFG_MACHINE_ID, candidate)
        return candidate

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def _verify_signature(self, payload_str, signature_hex):
        """Ed25519 verify(<payload_str bytes>, hex-decoded signature)."""
        try:
            with open(_PUBKEY_PATH, 'rb') as f:
                pem = f.read()
            pubkey = serialization.load_pem_public_key(pem)
        except (OSError, ValueError) as e:
            _logger.error('saas_license_gate: cannot load pubkey: %s', e)
            return False
        if not isinstance(pubkey, Ed25519PublicKey):
            _logger.error('saas_license_gate: pubkey is not Ed25519')
            return False
        try:
            sig_bytes = bytes.fromhex(signature_hex)
        except (TypeError, ValueError):
            return False
        try:
            pubkey.verify(sig_bytes, payload_str.encode('utf-8'))
            return True
        except InvalidSignature:
            return False

    # ------------------------------------------------------------------
    # Public verdict accessors (called by enforcement decorators)
    # ------------------------------------------------------------------

    @api.model
    def current_status(self):
        """Return (status_str, payload_dict_or_none). Stale beyond
        _STALE_THRESHOLD_SECONDS is reported as 'stale'."""
        ICP = self.env['ir.config_parameter'].sudo()
        status = ICP.get_param(_CFG_STATUS) or _STATUS_BAD_SIGNATURE
        checked_at_str = ICP.get_param(_CFG_CHECKED_AT) or '0'
        try:
            checked_at = int(checked_at_str)
        except ValueError:
            checked_at = 0
        if checked_at and (time.time() - checked_at) > _STALE_THRESHOLD_SECONDS:
            return _STATUS_STALE, None
        payload_str = ICP.get_param(_CFG_PAYLOAD)
        payload = None
        if payload_str:
            try:
                payload = json.loads(payload_str)
            except ValueError:
                payload = None
        return status, payload

    @api.model
    def currently_valid(self):
        status, _ = self.current_status()
        return status in (_STATUS_ACTIVE, _STATUS_GRACE)

    @api.model
    def currently_in_grace(self):
        status, _ = self.current_status()
        return status == _STATUS_GRACE

    @api.model
    def allowed_modules(self):
        _, payload = self.current_status()
        if not payload:
            return []
        return payload.get('allowed_modules') or []
