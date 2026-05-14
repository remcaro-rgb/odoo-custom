{
    'name': 'SaaS Filestore Backup',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Nightly tar+encrypt+upload of the tenant filestore to the WARM S3 bucket',
    'description': """
SaaS Filestore Backup
=====================

Closes the only-Postgres-is-backed-up gap in the Phase-1 backup story. The
``backup-runner`` sidecar that was supposed to handle filestore tar+upload
turned out to be a non-starter on Railway (volumes attach to exactly one
service — the runner can't see the Odoo container's filestore). This addon
runs the backup logic FROM INSIDE the Odoo container, where the filestore is
local on disk and the per-tenant DEK is available via the gate addon's
existing telemetry endpoint.

How it works (per-tenant cron, daily at 03:30 COT == 08:30 UTC):

1. Read the tenant's ``saas.tenant_id``, ``saas.telemetry_secret``, and
   ``saas.filestore_backup_endpoint`` from ``ir.config_parameter``. If the
   endpoint isn't set, log + skip (development environments + new tenants
   before the control plane wires the secret).
2. Tar the filestore directory at ``filestore_path()`` (typically
   ``/var/lib/odoo/filestore/<db_name>``).
3. Pull the tenant's per-tenant DEK from the control plane via an
   HMAC-authenticated GET against ``saas.filestore_backup_endpoint``. The
   endpoint returns a one-shot envelope with the plaintext DEK + an S3 PUT
   pre-signed URL.
4. AES-256-GCM encrypt the tar with the DEK, stream upload to the
   pre-signed URL.
5. POST the resulting metadata (sha256, size, S3 key, GCM nonce + tag,
   completed_at) back to the control plane so a row lands in
   ``tenant_backups``.

Phase 1 ships the addon skeleton + the cron entry, with the per-step logic
marked TODO. Phase 2 wires the real S3 + control-plane endpoints (the WDK
backup pipeline is the model — `packages/workflows/src/tenant-backup-daily.ts`
on the control-plane side already covers most of the encryption + upload
contract).
""",
    'author': 'Goliatt',
    'license': 'LGPL-3',
    'depends': ['saas_tenant_gate'],
    'data': [
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    # Auto-install alongside saas_tenant_gate so every provisioned tenant
    # picks it up without an extra step in provisionTenant.
    'auto_install': True,
}
