// POST /v1/admin-ops — Fly-resident proxy for cluster + Redis ops that
// the workflow on Vercel can't reach over 6PN.
//
// Phase 3.0 v0.4. Closes the two warned-but-not-blocking gaps that
// drill #16.13 surfaced: moveTier's swapTraefik step couldn't talk to
// `odoo-saas-redis.internal:6379` from Vercel, and the
// dropSourceAndFinalize step couldn't talk to
// `odoo-saas-postgres.internal:5432`. The runner sits on Fly's 6PN
// and reaches both — make it a small RPC proxy for those two
// operations.
//
// Actions (single endpoint, action discriminator in body):
//
//   { "action": "register-route",
//     "hostname": "<slug>.fly.app.goliatt.co",
//     "upstream": "odoo-saas-odoo-<slug>.internal:8069",
//     "headers": { "X-Odoo-Database": "<slug>" } }
//
//   { "action": "drop-db",
//     "dbName": "<tenant-db-name>",
//     "cluster": { "host", "port?", "user?", "password?" }   // optional;
//                                                             // omitted = runner's default (shared)
//   }
//
// Auth: same bearer token as the rest of /v1/*. Cheap to add and
// keeps the WDK workflow path stable (one runner-client per logical
// operation, no per-action env plumbing).

import type { Handler } from 'hono';
import { z } from 'zod';

import { registerRouteViaRedis } from '../pipeline/traefik-route.js';
import { dropDatabaseViaPg } from '../pipeline/drop-db.js';

const registerRouteSchema = z.object({
  action: z.literal('register-route'),
  hostname: z.string().min(1),
  upstream: z.string().min(1),
  headers: z.record(z.string(), z.string()).optional(),
});

const dropDbSchema = z.object({
  action: z.literal('drop-db'),
  dbName: z.string().regex(/^[a-z][a-z0-9_-]{1,62}$/),
  cluster: z
    .object({
      host: z.string().min(1),
      port: z.number().int().min(1).max(65535).default(5432),
      user: z.string().min(1).optional(),
      password: z.string().min(1).optional(),
    })
    .optional(),
});

const bodySchema = z.discriminatedUnion('action', [registerRouteSchema, dropDbSchema]);

export const adminOpsHandler: Handler = async (c) => {
  const raw = await c.req.json();
  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return c.json({ error: 'invalid-request', detail: parsed.error.flatten() }, 400);
  }
  const input = parsed.data;

  try {
    if (input.action === 'register-route') {
      const redisUrl = process.env.FLY_TRAEFIK_REDIS_URL ?? process.env.TRAEFIK_REDIS_URL;
      const rootKey = process.env.FLY_TRAEFIK_ROOT_KEY ?? process.env.TRAEFIK_ROOT_KEY ?? 'traefik';
      if (!redisUrl) {
        return c.json({ error: 'traefik-redis-url-unset' }, 503);
      }
      await registerRouteViaRedis({
        redisUrl,
        rootKey,
        hostname: input.hostname,
        upstream: input.upstream,
        headers: input.headers,
      });
      return c.json({ ok: true, action: 'register-route', hostname: input.hostname });
    }

    if (input.action === 'drop-db') {
      const pgEnv: Record<string, string> = input.cluster
        ? {
            PGHOST: input.cluster.host,
            PGPORT: String(input.cluster.port),
            ...(input.cluster.user ? { PGUSER: input.cluster.user } : {}),
            ...(input.cluster.password ? { PGPASSWORD: input.cluster.password } : {}),
          }
        : {};
      await dropDatabaseViaPg({ dbName: input.dbName, env: pgEnv });
      return c.json({ ok: true, action: 'drop-db', dbName: input.dbName });
    }

    return c.json({ error: 'unreachable' }, 500);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`admin-ops failed: ${message}`);
    return c.json({ error: 'op-failed', detail: message }, 500);
  }
};
