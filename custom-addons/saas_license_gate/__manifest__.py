{
    'name': 'SaaS License Gate (Enterprise Self-Host)',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Verifies an Ed25519-signed license response on boot + daily; refuses to run when invalid',
    'description': """
SaaS License Gate
=================

Phase 4.1 v0.3 — the self-host counterpart to saas_tenant_gate.

This addon ships ONLY in the enterprise self-host image variant. It is
NOT installed in the shared SaaS pool image (where the operator already
controls runtime via the control plane).

What it does
------------

On every cron tick (hourly by default, configurable to daily) and on the
pre_init_hook (i.e., at the moment a brand-new database is being
initialized with this module), the addon POSTs to the control-plane
license authority::

    POST <LICENSE_AUTHORITY_URL>/api/internal/license/check
    {license_id, image_sha256, machine_id, timestamp}
    headers: x-saas-signature, x-saas-timestamp (HMAC-SHA256)

The control plane returns a payload signed with Ed25519::

    { payload: "<canonical-json>", signature: "<hex>" }

The addon verifies the signature against an embedded public key
(/etc/saas-license-pubkey.pem, COPY'd into the image during the GHCR
build). If verification fails — bad signature, license revoked,
expires_at past, image_sha256 mismatch — the addon flips a global flag
that makes:

  - account.move, sale.order, stock.picking, and a few other write-
    heavy models go read-only via a constraint.
  - The system bar surfaces a "License invalid: <status>" banner.

Grace mode (between expires_at and grace_until) leaves only account.move
writable — matching the DIAN regulatory requirement that customers must
remain able to close their books for the period they paid for, even if
they let the license lapse.

Configuration
-------------

Pulled from environment at boot time::

    LICENSE_ID           — UUID from the operator (license_id col).
    LICENSE_AUTHORITY_URL — e.g. https://admin.goliatt.co
    SAAS_PROVISIONING_SECRET — HMAC shared secret.
    ODOO_IMAGE_DIGEST    — image sha256 (set by GHCR build).

If LICENSE_ID is unset, the addon refuses to install (pre_init_hook
raises) so an unlicensed image can't bootstrap a fresh DB.

Security properties
-------------------

- HMAC alone is not sufficient: a leaked secret would let an attacker
  forge ``valid=true`` responses. The Ed25519 signature on the response
  is what we actually trust.
- The pubkey is baked into the image; rotating it means rebuilding +
  re-tagging the image (intentional — keeps key rotation tied to image
  promotion).
- machine_id (read from /etc/machine-id, or generated + persisted to
  ir.config_parameter on first boot) lets the operator audit which
  installation is calling home; it isn't currently used to enforce
  "one machine per license" but the schema supports it later.
""",
    'author': 'Goliatt',
    'license': 'LGPL-3',
    # Depends only on `base`; saas_tenant_gate is NOT a dep because this
    # addon ships in a different image variant. The two should never
    # both be installed in the same DB.
    'depends': ['base'],
    'data': [
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv',
    ],
    'pre_init_hook': 'pre_init_check',
    'installable': True,
    'application': False,
    'auto_install': False,
}
