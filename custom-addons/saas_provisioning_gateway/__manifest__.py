{
    'name': 'SaaS Provisioning Gateway',
    'version': '19.0.1.1.1',
    'category': 'Administration',
    'summary': 'HMAC-gated /saas/provision endpoint for control-plane tenant creation',
    'description': """
SaaS Provisioning Gateway
=========================

Lives in the **multi-tenant Odoo pool image** (NOT inside each tenant DB).
The SaaS control plane POSTs to ``/saas/provision`` to create a new tenant
database; the route bypasses Odoo's ``list_db=False`` block by calling the
underlying ``_create_empty_database`` + ``_initialize_db`` helpers directly
instead of going through the decorated ``exp_create_database``.

* **Auth** — HMAC-SHA256 over ``timestamp.body`` using the
  ``SAAS_PROVISIONING_SECRET`` env var. Five-minute drift window matches
  the existing ``saas_tenant_gate`` telemetry contract.
* **No-DB route** — registered before any tenant DB is selected, which is
  necessary because the route's whole job is creating the DB. Requires the
  addon to be in ``server_wide_modules`` (--load=...,saas_provisioning_gateway
  in the entrypoint).
* **Same image, dual platforms** — same secret on Railway + Fly so the
  control plane can target either pool with the same request shape.

Designed to coexist with ``list_db=False`` in odoo.conf. We DO NOT need
``/web/database/manager`` for production; this addon replaces that surface
with a control-plane-only one.
    """,
    'author': 'Manuel Caro',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [],
    # auto_install lets it install into any DB it's loaded against. For the
    # nodb /saas/provision route the controller is registered via the
    # --load entrypoint flag — see infra/odoo-entrypoint.sh. Setting
    # auto_install=False so we don't pollute tenant DBs that don't need it.
    'auto_install': False,
    'application': False,
    'installable': True,
}
