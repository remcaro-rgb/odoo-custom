import { serve } from '@hono/node-server';
import { Hono } from 'hono';

import { backupTenantHandler } from './handlers/backup-tenant.js';
import { restoreTenantHandler } from './handlers/restore-tenant.js';
import { countRowsHandler } from './handlers/count-rows.js';
import { adminOpsHandler } from './handlers/admin-ops.js';
import { healthHandler } from './handlers/health.js';
import { bearerAuth } from './auth.js';

const app = new Hono();

app.get('/health', healthHandler);

// Everything under /v1/ requires the runner bearer token.
app.use('/v1/*', bearerAuth);
app.post('/v1/backup-tenant', backupTenantHandler);
app.post('/v1/restore-tenant', restoreTenantHandler);
app.post('/v1/count-rows', countRowsHandler);
app.post('/v1/admin-ops', adminOpsHandler);

const port = Number(process.env.PORT ?? 8080);
serve({ fetch: app.fetch, port }, (info) => {
  console.log(`backup-runner listening on :${info.port}`);
});
