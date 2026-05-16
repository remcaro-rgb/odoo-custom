// Traefik route registration via Redis KV.
//
// Mirrors the layout used by packages/infra/src/traefik-routes.ts in the
// control plane (so a future control-plane reader of these keys sees
// the same shape). Each tenant gets a router + service + middleware
// triple under `<rootKey>/http/...`:
//
//   <root>/http/routers/<slug>/rule          HostRegexp(`{...}`) or Host(`<hostname>`)
//   <root>/http/routers/<slug>/service       <slug>
//   <root>/http/routers/<slug>/entrypoints/0 websecure
//   <root>/http/routers/<slug>/tls/certResolver letsencrypt
//   <root>/http/routers/<slug>/middlewares/0 saas-headers-<slug>   (when headers provided)
//   <root>/http/services/<slug>/loadbalancer/servers/0/url  http://<upstream>
//   <root>/http/middlewares/saas-headers-<slug>/headers/customRequestHeaders/X-Odoo-Database  <slug>
//
// On unregister, all keys under those prefixes are SCAN+DELed.

// ioredis ships its constructor as the default `Redis` export AND as
// `Redis` named — we use the default form here because TypeScript's
// strict moduleResolution disagrees with the `import Redis from 'ioredis'`
// shorthand when esModuleInterop is off in the runner's tsconfig.
import { Redis } from 'ioredis';

interface RegisterRouteArgs {
  redisUrl: string;
  rootKey: string;
  hostname: string;
  upstream: string;
  headers?: Record<string, string>;
}

/** Slug used as router/service name. Derived from the hostname's
 *  leftmost label (`acmesas2.fly.app.goliatt.co` → `acmesas2`).
 *  Keeps the Redis key layout flat + predictable. */
function slugFromHostname(hostname: string): string {
  return hostname.split('.')[0]!;
}

export async function registerRouteViaRedis(args: RegisterRouteArgs): Promise<void> {
  const slug = slugFromHostname(args.hostname);
  const root = args.rootKey.replace(/\/+$/, '');
  const routerPrefix = `${root}/http/routers/${slug}`;
  const servicePrefix = `${root}/http/services/${slug}`;
  const middlewareName = `saas-headers-${slug}`;
  const middlewarePrefix = `${root}/http/middlewares/${middlewareName}`;

  const redis = new Redis(args.redisUrl, {
    // Keep retries small — admin-ops returns to the caller quickly on
    // network failure so the operator sees the real error.
    maxRetriesPerRequest: 2,
    connectTimeout: 5000,
  });
  try {
    const pipeline = redis.pipeline();
    pipeline.set(`${routerPrefix}/rule`, `Host(\`${args.hostname}\`)`);
    pipeline.set(`${routerPrefix}/service`, slug);
    pipeline.set(`${routerPrefix}/entrypoints/0`, 'websecure');
    pipeline.set(`${routerPrefix}/tls/certResolver`, 'letsencrypt');
    pipeline.set(`${servicePrefix}/loadbalancer/servers/0/url`, `http://${args.upstream}`);

    if (args.headers && Object.keys(args.headers).length > 0) {
      pipeline.set(`${routerPrefix}/middlewares/0`, middlewareName);
      let i = 0;
      for (const [k, v] of Object.entries(args.headers)) {
        pipeline.set(`${middlewarePrefix}/headers/customRequestHeaders/${k}`, v);
        i += 1;
      }
      void i;
    } else {
      // Clean up any stale middleware refs in case the previous registration
      // had headers and this one doesn't.
      pipeline.del(`${routerPrefix}/middlewares/0`);
    }

    await pipeline.exec();
  } finally {
    redis.disconnect();
  }
}
