# Promote second-region replica to primary

Stub. Triggered when the primary region is unreachable. Steps:

1. Confirm primary is down (not a network blip) — check pgBackRest WAL
   archive gap; > 7 min without a new segment + control plane unreachable =
   true outage.
2. On the standby:
   `SELECT pg_promote(wait => true, wait_seconds => 60);`
3. Update Traefik dynamic config (Redis KV) so all tenant routes point at the
   promoted region.
4. Update `odoo_instances.postgres_dsn_ref` in the Neon control-plane DB.
5. Re-point Odoo pool deployments (rolling restart on Railway / Fly).
6. After primary recovery: rebuild old primary as a streaming replica off the
   new primary. Do **not** demote-and-swap blindly — verify WAL alignment.

RTO target: < 30 minutes.
