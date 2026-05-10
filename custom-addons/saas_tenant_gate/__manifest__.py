{
    'name': 'SaaS Tenant Gate',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Per-tenant SaaS controls: seat enforcement, telemetry, feature flags',
    'description': """
SaaS Tenant Gate
================

Runs in every hosted tenant database. Owned by the SaaS operator, not the
tenant. Three responsibilities:

* **Seat cap enforcement** — overrides ``res.users.create`` to block new
  internal users beyond the cap stored in ``ir.config_parameter`` under
  ``saas.seat_cap``. Portal users (``share=True``) and inactive users are
  not counted. Rejections are recorded in ``ir.logging`` for audit.
* **Telemetry** — exposes ``/saas/telemetry`` as an HMAC-authenticated
  endpoint that returns the tenant's seat count, installed modules, and
  configured plan code. The shared secret lives in
  ``saas.telemetry_secret``.
* **Health** — exposes ``/saas/health`` as an unauthenticated platform
  liveness probe.

Configured entirely via ``ir.config_parameter`` keys with the ``saas.``
prefix; the SaaS control plane writes those keys during provisioning.
    """,
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'data/ir_config_parameter.xml',
    ],
    'auto_install': True,
    'application': False,
    'installable': True,
}
