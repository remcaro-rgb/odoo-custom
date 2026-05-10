# PITR restore

Stub. Triggered by the WDK `tenantRestore` workflow (manual, dual-approved)
or run by hand for forensic restores into a sandbox.

Target time: < 30 min for typical tenant DB (500 MB – 5 GB).

Steps:

1. Identify the recovery target — wall-clock time or LSN — from the
   `tenant_backups` catalog row.
2. Provision a sandbox Postgres instance (same image, same config). Mount an
   empty volume.
3. `pgbackrest --stanza=shared --type=time --target="<ISO timestamp>" restore`.
4. Start Postgres. It will replay WAL from the archive up to the target.
5. Connect Odoo against the sandbox, hit `/web/health`, count rows on
   `account.move` / `res.users` / `ir.attachment` to sanity-check.
6. Either: (a) promote sandbox as the new primary for the tenant by updating
   `odoo_instances.postgres_dsn_ref`, or (b) `pg_dump` the relevant tables
   for surgical restore into the live DB.

**Never restore directly over a live tenant DB without dual approval** — the
WDK `tenantRestore` workflow enforces this via `createHook`.
