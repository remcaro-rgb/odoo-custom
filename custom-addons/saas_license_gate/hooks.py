"""pre_init_hook — refuse to install on an unlicensed image.

Runs once at module install time. If the image isn't carrying the
required configuration (LICENSE_ID env var + the embedded public key
file at /etc/saas-license-pubkey.pem), the install aborts. This keeps
a copied-without-paying image from bootstrapping a fresh database.

Note: pre_init_hook ONLY runs on module install/update. For ongoing
enforcement after first install we rely on the hourly ir.cron in
data/ir_cron_data.xml. The hook is a one-shot gate, not the runtime
verdict.
"""

import logging
import os

_logger = logging.getLogger(__name__)

_PUBKEY_PATH = '/etc/saas-license-pubkey.pem'
_LICENSE_ID_ENV = 'LICENSE_ID'
_AUTHORITY_URL_ENV = 'LICENSE_AUTHORITY_URL'


def pre_init_check(env):
    """Odoo 19 passes the env object to pre_init_hook (older versions
    passed the cursor; this signature works in both via env-or-cr
    detection)."""
    # Backward-compat: old Odoo passes cr; accept either.
    license_id = (os.environ.get(_LICENSE_ID_ENV) or '').strip()
    authority = (os.environ.get(_AUTHORITY_URL_ENV) or '').strip()

    if not license_id:
        raise RuntimeError(
            'saas_license_gate refuses to install: '
            'LICENSE_ID environment variable is not set. '
            'This image is intended for licensed enterprise self-host '
            'deployments. Contact your operator for a license ID.'
        )
    if not authority:
        raise RuntimeError(
            'saas_license_gate refuses to install: '
            'LICENSE_AUTHORITY_URL environment variable is not set.'
        )
    if not os.path.isfile(_PUBKEY_PATH):
        raise RuntimeError(
            'saas_license_gate refuses to install: '
            f'no signing public key found at {_PUBKEY_PATH}. The image was built '
            'without infra/keys/license-signing-pubkey.pem — this is a '
            'packaging error, not a customer-side problem.'
        )
    _logger.info(
        'saas_license_gate: pre_init_hook OK — license_id=%s authority=%s',
        license_id[:8] + '…', authority,
    )
