# Postgres major version upgrade

Stub. Filled in before the first major upgrade (16 → 17). Outline:

1. Cut a fresh base backup + verify restore-from-backup on a staging instance.
2. Spin up the new-version Postgres on a parallel volume (`pgdata.next`).
3. `pg_upgrade --link` after stopping the old primary (downtime window).
4. Bring new primary online, point Odoo connection strings to the new service.
5. Run `ANALYZE` across all DBs.
6. Retire the old volume after 7 days of successful operation.

Downtime budget: < 30 minutes. Schedule during the tenant-defined maintenance
window declared in `tenants.maintenance_window`.
