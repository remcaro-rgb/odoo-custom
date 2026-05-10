# Postgres runbooks

Operator playbooks for the self-managed Postgres service that backs the Odoo
SaaS data plane. Same procedures apply on Railway Volumes and Fly Volumes —
the image is identical; only the platform-specific service descriptor differs.

| Runbook | When to run |
|---|---|
| [upgrade.md](upgrade.md) | Major Postgres version bump (16 → 17). |
| [vacuum-freeze.md](vacuum-freeze.md) | Suspected transaction-ID wraparound risk. |
| [replica-promote.md](replica-promote.md) | Primary region outage; promote second-region standby. |
| [disk-resize.md](disk-resize.md) | Volume nearing capacity. |
| [restore-pitr.md](restore-pitr.md) | PITR restore from WAL + base backup. |

All runbooks assume:
- `pgbackrest --stanza=shared check` returns clean before you start.
- You have shell into the Postgres service on the target platform.
- An on-call peer is paired for any operation that touches the primary.
