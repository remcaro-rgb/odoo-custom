# License-Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first operator-facing UI slice inside `apps/admin` of the control plane — license CRUD with full `license-cli.sh` parity, a generic audit-log viewer, and a `/v1/check` signing-key probe.

**Architecture:** Next 16 App Router with Server Components for reads (data fetched in-process via `appRouter.createCaller`) and Server Actions for mutations. Client islands only for filter inputs, dialogs, and form interactions. Auth is layered: Clerk middleware → server-side AuthGate in layout → tRPC operator procedure → defense-in-depth check inside each server action.

**Tech Stack:** Next 16, React 19, tRPC v11, Drizzle ORM, @neondatabase/serverless, Clerk, Tailwind v4, shadcn/ui, @tanstack/react-table, sonner (toasts), react-hook-form, zod, vitest (unit + integration), Playwright (E2E).

**Source spec:** `docs/superpowers/specs/2026-05-17-license-management-ui-design.md`

**Repository layout note:** The data plane lives at `/Volumes/SATECHI2TB/userfolder/Odoo` (this repo). The control plane is a separate repo at `/Volumes/SATECHI2TB/userfolder/Odoo-control-plane`. Almost every task in this plan touches the control plane. When a task says "in the control plane," `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane` first. Commits in that repo live in its own git history; pushes go to its own remote.

---

## Task 1: Bootstrap vitest in `packages/api`

**Files:**
- Modify: `packages/api/package.json`
- Create: `packages/api/vitest.config.ts`
- Create: `packages/api/test/smoke.test.ts`

- [ ] **Step 1: Add vitest devDeps**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
pnpm --filter @odoo-saas/api add -D vitest @vitest/coverage-v8
```

- [ ] **Step 2: Add `test` script to `packages/api/package.json`**

Modify the `scripts` block to:

```json
"scripts": {
  "lint": "eslint .",
  "typecheck": "tsc --noEmit",
  "test": "vitest run",
  "test:watch": "vitest"
}
```

- [ ] **Step 3: Create `packages/api/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts', 'src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts'],
    },
  },
});
```

- [ ] **Step 4: Smoke test**

Create `packages/api/test/smoke.test.ts`:

```ts
import { describe, expect, it } from 'vitest';

describe('vitest smoke', () => {
  it('runs', () => {
    expect(2 + 2).toBe(4);
  });
});
```

- [ ] **Step 5: Verify it runs**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/api test`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add packages/api/package.json packages/api/vitest.config.ts packages/api/test/smoke.test.ts pnpm-lock.yaml
git commit -m "chore(api): bootstrap vitest for unit + integration tests"
```

---

## Task 2: Extend `enterpriseLicenses.list` for dashboard reads (TDD)

**Files:**
- Modify: `packages/api/src/routers/enterprise-licenses.ts`
- Create: `packages/api/test/enterprise-licenses-list.test.ts`

The dashboard's unfiltered first render needs `customerRef` AND `imageSha256` to be optional, plus a `status` filter, `from`/`to` (`createdAt` range), and cursor pagination.

- [ ] **Step 1: Write failing test for unfiltered list**

Create `packages/api/test/enterprise-licenses-list.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest';

// Mock the db before importing the router
const mockQuery = vi.fn();
vi.mock('@odoo-saas/db', () => ({
  db: {
    select: vi.fn(() => ({
      from: vi.fn(() => ({
        where: vi.fn(() => ({
          orderBy: vi.fn(() => ({
            limit: vi.fn(() => mockQuery()),
          })),
        })),
      })),
    })),
  },
  schema: {
    enterpriseLicenses: {
      id: 'id',
      customerRef: 'customer_ref',
      imageSha256: 'image_sha256',
      expiresAt: 'expires_at',
      graceUntil: 'grace_until',
      revokedAt: 'revoked_at',
      createdAt: 'created_at',
    },
  },
}));

import { enterpriseLicensesRouter } from '../src/routers/enterprise-licenses';

const operatorCtx = {
  req: new Request('http://localhost'),
  session: { userId: 'user_test', isOperator: true },
};

beforeEach(() => {
  mockQuery.mockReset();
});

describe('enterpriseLicenses.list', () => {
  it('accepts an empty filter and returns most-recent rows', async () => {
    mockQuery.mockResolvedValue([
      { id: 'a', customerRef: 'acme', imageSha256: 'abc', createdAt: new Date('2026-05-01'), expiresAt: new Date('2027-05-01'), graceUntil: new Date('2027-05-15'), revokedAt: null },
    ]);
    const caller = enterpriseLicensesRouter.createCaller(operatorCtx);
    const result = await caller.list({});
    expect(result).toHaveLength(1);
    expect(result[0].customerRef).toBe('acme');
  });
});
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/api test enterprise-licenses-list`
Expected: FAIL with "supply at least one filter" (current `.refine()` enforces this).

- [ ] **Step 3: Relax the `refine` and extend the schema**

In `packages/api/src/routers/enterprise-licenses.ts`, find the `list` procedure (search for `list: operatorProcedure`) and replace its `.input(...)` block:

```ts
.input(
  z
    .object({
      customerRef: customerRefSchema.optional(),
      imageSha256: imageDigestSchema.optional(),
      status: z.enum(['active', 'grace', 'expired', 'revoked', 'all']).optional(),
      from: z.string().datetime().optional(),
      to: z.string().datetime().optional(),
      cursor: z.string().optional(),
      limit: z.number().int().min(1).max(200).default(50),
    })
    .default({}),
)
```

Note: the `.refine()` requiring at least one of customerRef/imageSha256 is removed entirely.

- [ ] **Step 4: Implement filter compilation in the query body**

Inside the same `list` procedure's `.query(async ({ input }) => { ... })`, replace the body with:

```ts
const conds = [];
if (input.customerRef) {
  conds.push(eq(schema.enterpriseLicenses.customerRef, input.customerRef));
}
if (input.imageSha256) {
  conds.push(eq(schema.enterpriseLicenses.imageSha256, input.imageSha256));
}
if (input.from) {
  conds.push(sql`${schema.enterpriseLicenses.createdAt} >= ${new Date(input.from)}`);
}
if (input.to) {
  conds.push(sql`${schema.enterpriseLicenses.createdAt} <= ${new Date(input.to)}`);
}
const now = sql`now()`;
switch (input.status) {
  case 'active':
    conds.push(sql`${schema.enterpriseLicenses.revokedAt} IS NULL`);
    conds.push(sql`${schema.enterpriseLicenses.expiresAt} > ${now}`);
    break;
  case 'grace':
    conds.push(sql`${schema.enterpriseLicenses.revokedAt} IS NULL`);
    conds.push(sql`${schema.enterpriseLicenses.expiresAt} <= ${now}`);
    conds.push(sql`${schema.enterpriseLicenses.graceUntil} > ${now}`);
    break;
  case 'expired':
    conds.push(sql`${schema.enterpriseLicenses.revokedAt} IS NULL`);
    conds.push(sql`${schema.enterpriseLicenses.graceUntil} <= ${now}`);
    break;
  case 'revoked':
    conds.push(sql`${schema.enterpriseLicenses.revokedAt} IS NOT NULL`);
    break;
  case 'all':
  case undefined:
    break;
}
// Cursor: opaque base64 of `<createdAt-iso>|<id>`
if (input.cursor) {
  const decoded = Buffer.from(input.cursor, 'base64').toString('utf-8');
  const [cursorTs, cursorId] = decoded.split('|');
  if (cursorTs && cursorId) {
    conds.push(
      sql`(${schema.enterpriseLicenses.createdAt}, ${schema.enterpriseLicenses.id}) < (${new Date(cursorTs)}, ${cursorId})`,
    );
  }
}
const rows = await db
  .select()
  .from(schema.enterpriseLicenses)
  .where(conds.length ? and(...conds) : undefined)
  .orderBy(desc(schema.enterpriseLicenses.createdAt), desc(schema.enterpriseLicenses.id))
  .limit(input.limit);

const nextCursor =
  rows.length === input.limit
    ? Buffer.from(`${rows[rows.length - 1].createdAt.toISOString()}|${rows[rows.length - 1].id}`).toString('base64')
    : null;
return { rows, nextCursor };
```

Add the `sql` import at the top: change `import { and, desc, eq } from 'drizzle-orm';` to `import { and, desc, eq, sql } from 'drizzle-orm';`.

**Breaking change note:** the return shape changes from `Row[]` to `{ rows: Row[], nextCursor: string | null }`. `license-cli.sh list-by-customer` and `list-by-image` use the HTTP route at `/api/internal/license/list` — verify those callers don't break in Task 2b below.

- [ ] **Step 5: Check `/api/internal/license/list` HTTP route consumers**

Run: `grep -rn 'enterpriseLicenses\.list\|/api/internal/license/list' apps packages | grep -v test`
Expected output: identify the HTTP route handler and any other callers.

If `apps/admin/app/api/internal/license/list/route.ts` extracts `.rows`, update it to handle the new shape. If it returns the result directly, update the bash CLI test or accept the shape change in CLI. Inspect:

```bash
cat apps/admin/app/api/internal/license/list/route.ts
```

If the route returned the bare array before, adjust to return `result.rows` for CLI backward compat:

```ts
// In the route handler, after `await caller.enterpriseLicenses.list(input)`:
const { rows } = await caller.enterpriseLicenses.list(input);
return Response.json(rows);
```

- [ ] **Step 6: Re-run the failing test — expect PASS**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/api test enterprise-licenses-list`
Expected: PASS.

- [ ] **Step 7: Add tests for status filtering**

Append to `packages/api/test/enterprise-licenses-list.test.ts`:

```ts
describe('enterpriseLicenses.list — status filter', () => {
  // We don't validate exact SQL here (Drizzle composes opaquely). We validate
  // the procedure accepts each status value and returns whatever the mocked
  // DB returns. SQL correctness is covered by the integration tests in
  // Task 18 against a real Neon branch.
  for (const status of ['active', 'grace', 'expired', 'revoked', 'all'] as const) {
    it(`accepts status=${status}`, async () => {
      mockQuery.mockResolvedValue([]);
      const caller = enterpriseLicensesRouter.createCaller(operatorCtx);
      const result = await caller.list({ status });
      expect(result.rows).toEqual([]);
      expect(result.nextCursor).toBeNull();
    });
  }
});
```

Run: `pnpm --filter @odoo-saas/api test enterprise-licenses-list`
Expected: 6 passing.

- [ ] **Step 8: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add packages/api/src/routers/enterprise-licenses.ts \
        packages/api/test/enterprise-licenses-list.test.ts \
        apps/admin/app/api/internal/license/list/route.ts
git commit -m "feat(api): extend enterpriseLicenses.list with status/cursor/dates

Adds optional status (active|grace|expired|revoked|all), from/to date
range, and base64 cursor pagination. customerRef + imageSha256 now both
optional. Return shape gains a nextCursor; the HTTP route still returns
the bare rows array for CLI backward compat."
```

---

## Task 3: Add `audit` tRPC router (TDD)

**Files:**
- Create: `packages/api/src/routers/audit.ts`
- Modify: `packages/api/src/routers/_app.ts`
- Create: `packages/api/test/audit-list.test.ts`

- [ ] **Step 1: Write failing test**

Create `packages/api/test/audit-list.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockQuery = vi.fn();
vi.mock('@odoo-saas/db', () => ({
  db: {
    select: vi.fn(() => ({
      from: vi.fn(() => ({
        where: vi.fn(() => ({
          orderBy: vi.fn(() => ({
            limit: vi.fn(() => mockQuery()),
          })),
        })),
      })),
    })),
  },
  schema: {
    auditLog: {
      id: 'id',
      ts: 'ts',
      actorUserId: 'actor_user_id',
      action: 'action',
      targetType: 'target_type',
      targetId: 'target_id',
      payload: 'payload',
    },
  },
}));

import { auditRouter } from '../src/routers/audit';

const operatorCtx = {
  req: new Request('http://localhost'),
  session: { userId: 'user_test', isOperator: true },
};

beforeEach(() => mockQuery.mockReset());

describe('audit.list', () => {
  it('returns rows + nextCursor for empty filter', async () => {
    mockQuery.mockResolvedValue([
      { id: 'a', ts: new Date('2026-05-17'), actorUserId: 'user_op', action: 'license.issue', targetType: 'license', targetId: 'lic_a', payload: {} },
    ]);
    const caller = auditRouter.createCaller(operatorCtx);
    const result = await caller.list({});
    expect(result.rows).toHaveLength(1);
    expect(result.nextCursor).toBeNull();
  });

  it('non-operator gets FORBIDDEN', async () => {
    const caller = auditRouter.createCaller({
      ...operatorCtx,
      session: { userId: 'u', isOperator: false },
    });
    await expect(caller.list({})).rejects.toThrow(/operator role required/);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/api test audit-list`
Expected: FAIL (module `../src/routers/audit` not found).

- [ ] **Step 3: Implement `packages/api/src/routers/audit.ts`**

```ts
// Audit log query surface — operator-only, generic across all action
// namespaces (license.*, tenant.*, backup.*, email.*, ...). The UI's
// /audit page uses this; future per-entity drill-down pages can also
// call it with a targetId filter.

import { and, desc, sql } from 'drizzle-orm';
import { z } from 'zod';

import { db, schema } from '@odoo-saas/db';

import { operatorProcedure, router } from '../trpc';

const ACTION_NAMESPACES = ['license', 'tenant', 'backup', 'email'] as const;

export const auditRouter = router({
  list: operatorProcedure
    .input(
      z
        .object({
          actionPrefix: z.enum(ACTION_NAMESPACES).optional(),
          targetType: z.string().min(1).max(40).optional(),
          targetId: z.string().min(1).max(120).optional(),
          actor: z.string().min(1).max(80).optional(),
          from: z.string().datetime().optional(),
          to: z.string().datetime().optional(),
          cursor: z.string().optional(),
          limit: z.number().int().min(1).max(200).default(50),
        })
        .default({}),
    )
    .query(async ({ input }) => {
      const conds = [];
      if (input.actionPrefix) {
        conds.push(sql`${schema.auditLog.action} LIKE ${input.actionPrefix + '.%'}`);
      }
      if (input.targetType) {
        conds.push(sql`${schema.auditLog.targetType} = ${input.targetType}`);
      }
      if (input.targetId) {
        conds.push(sql`${schema.auditLog.targetId} = ${input.targetId}`);
      }
      if (input.actor) {
        conds.push(sql`${schema.auditLog.actorUserId} = ${input.actor}`);
      }
      if (input.from) {
        conds.push(sql`${schema.auditLog.ts} >= ${new Date(input.from)}`);
      }
      if (input.to) {
        conds.push(sql`${schema.auditLog.ts} <= ${new Date(input.to)}`);
      }
      if (input.cursor) {
        const decoded = Buffer.from(input.cursor, 'base64').toString('utf-8');
        const [cursorTs, cursorId] = decoded.split('|');
        if (cursorTs && cursorId) {
          conds.push(
            sql`(${schema.auditLog.ts}, ${schema.auditLog.id}) < (${new Date(cursorTs)}, ${cursorId})`,
          );
        }
      }
      const rows = await db
        .select()
        .from(schema.auditLog)
        .where(conds.length ? and(...conds) : undefined)
        .orderBy(desc(schema.auditLog.ts), desc(schema.auditLog.id))
        .limit(input.limit);

      const nextCursor =
        rows.length === input.limit
          ? Buffer.from(`${rows[rows.length - 1].ts.toISOString()}|${rows[rows.length - 1].id}`).toString('base64')
          : null;
      return { rows, nextCursor };
    }),
});
```

- [ ] **Step 4: Register the router in `_app.ts`**

In `packages/api/src/routers/_app.ts`, add the import + the router key:

```ts
import { auditRouter } from './audit';
// ... other imports

export const appRouter = router({
  health: publicProcedure.query(() => ({ ok: true, ts: Date.now() })),
  tenants: tenantsRouter,
  tenantDomains: tenantDomainsRouter,
  plans: plansRouter,
  billing: billingRouter,
  signup: signupRouter,
  enterpriseLicenses: enterpriseLicensesRouter,
  audit: auditRouter,
});
```

- [ ] **Step 5: Run — expect PASS**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/api test audit-list`
Expected: 2 passing.

- [ ] **Step 6: Run typecheck**

Run: `pnpm --filter @odoo-saas/api typecheck`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add packages/api/src/routers/audit.ts \
        packages/api/src/routers/_app.ts \
        packages/api/test/audit-list.test.ts
git commit -m "feat(api): add generic audit.list router

Operator-only read query over the existing audit_log table with filters
for action namespace, target_type, target_id, actor, date range; cursor
pagination identical to enterpriseLicenses.list."
```

---

## Task 4: Bootstrap Tailwind v4 in `apps/admin`

**Files:**
- Modify: `apps/admin/package.json`
- Create: `apps/admin/app/globals.css`
- Modify: `apps/admin/app/layout.tsx`
- Create: `apps/admin/postcss.config.mjs`

Tailwind v4 ships with Next 16 but isn't preinstalled in this scaffold — Phase 1 step 10 explicitly skipped UI library setup.

- [ ] **Step 1: Install Tailwind v4 + PostCSS**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
pnpm --filter @odoo-saas/admin add -D tailwindcss@^4 @tailwindcss/postcss postcss
```

- [ ] **Step 2: Create `apps/admin/postcss.config.mjs`**

```js
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};
```

- [ ] **Step 3: Create `apps/admin/app/globals.css`**

```css
@import "tailwindcss";

@theme {
  --color-background: oklch(1 0 0);
  --color-foreground: oklch(0.145 0 0);
  --color-card: oklch(1 0 0);
  --color-card-foreground: oklch(0.145 0 0);
  --color-primary: oklch(0.205 0 0);
  --color-primary-foreground: oklch(0.985 0 0);
  --color-secondary: oklch(0.97 0 0);
  --color-secondary-foreground: oklch(0.205 0 0);
  --color-muted: oklch(0.97 0 0);
  --color-muted-foreground: oklch(0.556 0 0);
  --color-accent: oklch(0.97 0 0);
  --color-accent-foreground: oklch(0.205 0 0);
  --color-destructive: oklch(0.577 0.245 27.325);
  --color-destructive-foreground: oklch(0.985 0 0);
  --color-border: oklch(0.922 0 0);
  --color-input: oklch(0.922 0 0);
  --color-ring: oklch(0.708 0 0);
  --radius: 0.5rem;
}

body {
  font-family: ui-sans-serif, system-ui, sans-serif;
  color: var(--color-foreground);
  background: var(--color-background);
}
```

- [ ] **Step 4: Import globals.css in layout**

Find the current `apps/admin/app/layout.tsx`. Add at the top of the file (before any other imports):

```tsx
import './globals.css';
```

- [ ] **Step 5: Verify dev server compiles**

Run in a separate terminal: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/admin dev`
Open http://localhost:3001 — expected: hello-world page renders with system font, no console errors.

Stop the dev server when verified.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/package.json apps/admin/postcss.config.mjs \
        apps/admin/app/globals.css apps/admin/app/layout.tsx \
        pnpm-lock.yaml
git commit -m "feat(admin): bootstrap Tailwind v4 + globals.css"
```

---

## Task 5: Initialize shadcn/ui and install primitives

**Files:**
- Create: `apps/admin/components.json`
- Create: `apps/admin/lib/utils.ts`
- Create: `apps/admin/components/ui/*.tsx` (multiple)

- [ ] **Step 1: Run shadcn init**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane/apps/admin
npx shadcn@latest init -y -d --base-color neutral
```

This writes `components.json`, `lib/utils.ts`, and adds the necessary CSS variables. Accept all defaults; the script is non-interactive with `-y`.

If the script asks about the existing `globals.css`, choose to merge — keeping the @theme block from Task 4.

- [ ] **Step 2: Install primitive components used by the UI**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane/apps/admin
npx shadcn@latest add table badge button input textarea label select dialog alert-dialog dropdown-menu tabs card sonner form popover calendar
```

This drops files into `apps/admin/components/ui/`. About 15 files, ~40 KB of source.

- [ ] **Step 3: Install peer deps for @tanstack/react-table (used in our LicenseTable + AuditTable)**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
pnpm --filter @odoo-saas/admin add @tanstack/react-table date-fns
```

- [ ] **Step 4: Verify dev server still compiles**

Run: `pnpm --filter @odoo-saas/admin dev` and load http://localhost:3001
Expected: page renders, no console errors. Stop dev server when verified.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/components.json apps/admin/lib/utils.ts \
        apps/admin/components/ui/ apps/admin/package.json \
        apps/admin/app/globals.css pnpm-lock.yaml
git commit -m "feat(admin): init shadcn/ui + primitives (table, dialog, form, ...)"
```

---

## Task 6: Server-side tRPC caller + operator auth gate

**Files:**
- Create: `apps/admin/lib/trpc-server.ts`
- Create: `apps/admin/lib/auth/operator-gate.ts`

These are the two shared helpers every Server Component will use.

- [ ] **Step 1: Create the tRPC caller helper**

`apps/admin/lib/trpc-server.ts`:

```ts
import { cache } from 'react';
import { headers } from 'next/headers';
import { auth, clerkClient } from '@clerk/nextjs/server';

import { appRouter, createContext } from '@odoo-saas/api';

/**
 * Build a per-request tRPC caller for use inside Server Components.
 *
 * Cached via React.cache() so multiple components in the same request
 * tree resolve the Clerk session exactly once. The caller itself is
 * cheap to construct; the underlying Clerk lookup costs ~80 ms.
 */
export const getServerCaller = cache(async () => {
  const { userId } = await auth();
  let session: { userId: string; isOperator: boolean } | null = null;
  if (userId) {
    const user = await clerkClient.users.getUser(userId);
    session = {
      userId,
      isOperator: user.publicMetadata?.role === 'operator',
    };
  }
  const reqHeaders = await headers();
  const req = new Request('http://internal/', { headers: reqHeaders });
  return appRouter.createCaller(createContext({ req, session }));
});
```

- [ ] **Step 2: Create the operator auth gate**

`apps/admin/lib/auth/operator-gate.ts`:

```ts
import { cache } from 'react';
import { redirect } from 'next/navigation';
import { auth, clerkClient } from '@clerk/nextjs/server';

/**
 * Server-side operator gate.
 *
 * Resolves the Clerk session; redirects to /not-authorized for any
 * authenticated user whose publicMetadata.role !== 'operator'.
 * Unauthenticated users are caught by the Clerk middleware in proxy.ts
 * before reaching here.
 *
 * Cached per request so layouts + pages can both call it without
 * paying the Clerk lookup twice.
 */
export const requireOperator = cache(async () => {
  const { userId } = await auth();
  if (!userId) {
    // Defense-in-depth; middleware should have caught this already.
    redirect('/sign-in');
  }
  const user = await clerkClient.users.getUser(userId);
  if (user.publicMetadata?.role !== 'operator') {
    redirect('/not-authorized');
  }
  return { userId, user };
});
```

- [ ] **Step 3: Run typecheck**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/admin typecheck`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/lib/trpc-server.ts apps/admin/lib/auth/operator-gate.ts
git commit -m "feat(admin): add tRPC server caller + operator auth gate helpers"
```

---

## Task 7: Layout shell with sidebar + AuthGate + /not-authorized

**Files:**
- Modify: `apps/admin/app/layout.tsx`
- Create: `apps/admin/components/app-shell.tsx`
- Create: `apps/admin/app/not-authorized/page.tsx`
- Modify: `apps/admin/app/page.tsx` (redirect to /licenses)

- [ ] **Step 1: Create the AppShell**

`apps/admin/components/app-shell.tsx`:

```tsx
import Link from 'next/link';
import { UserButton } from '@clerk/nextjs';

const NAV = [
  { href: '/licenses', label: 'Licenses' },
  { href: '/audit', label: 'Audit log' },
  { href: '/signing-key', label: 'Signing key' },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-56 border-r border-border bg-muted/30 px-4 py-6">
        <div className="mb-8">
          <h1 className="text-lg font-semibold">Goliatt admin</h1>
          <p className="text-xs text-muted-foreground">operator console</p>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto pt-6">
          <UserButton afterSignOutUrl="/sign-in" />
        </div>
      </aside>
      <main className="flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Update layout to call requireOperator + wrap in AppShell**

Replace the body of `apps/admin/app/layout.tsx` (keeping the ClerkProvider wrapping that already exists):

```tsx
import './globals.css';
import { ClerkProvider } from '@clerk/nextjs';
import { Toaster } from '@/components/ui/sonner';

import { AppShell } from '@/components/app-shell';
import { requireOperator } from '@/lib/auth/operator-gate';

export const metadata = { title: 'Goliatt admin' };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          <OperatorOnly>
            <AppShell>{children}</AppShell>
          </OperatorOnly>
          <Toaster />
        </body>
      </html>
    </ClerkProvider>
  );
}

async function OperatorOnly({ children }: { children: React.ReactNode }) {
  // requireOperator redirects unauthorized users; if it returns, we're operator.
  await requireOperator();
  return <>{children}</>;
}
```

**Caveat:** the operator gate runs in every layout render. When the user lands on `/not-authorized`, this would loop. Carve out the gate so it skips for `/not-authorized` and `/sign-in` — see step 3.

- [ ] **Step 3: Exclude /not-authorized from the gate**

Make `apps/admin/app/not-authorized/` its own route group OUTSIDE the gated layout. Move the gate into a sub-layout instead.

Replace `apps/admin/app/layout.tsx` with the ungated version:

```tsx
import './globals.css';
import { ClerkProvider } from '@clerk/nextjs';
import { Toaster } from '@/components/ui/sonner';

export const metadata = { title: 'Goliatt admin' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          {children}
          <Toaster />
        </body>
      </html>
    </ClerkProvider>
  );
}
```

Create a route group `apps/admin/app/(operator)/layout.tsx` that holds the gate + AppShell:

```tsx
import { AppShell } from '@/components/app-shell';
import { requireOperator } from '@/lib/auth/operator-gate';

export default async function OperatorLayout({ children }: { children: React.ReactNode }) {
  await requireOperator();
  return <AppShell>{children}</AppShell>;
}
```

All operator pages (licenses, audit, signing-key) live under `app/(operator)/`. `/not-authorized` lives at `app/not-authorized/page.tsx` outside the group.

- [ ] **Step 4: Move admin's hello-world page to redirect**

Replace `apps/admin/app/page.tsx`:

```tsx
import { redirect } from 'next/navigation';

export default function AdminHome() {
  redirect('/licenses');
}
```

- [ ] **Step 5: Create /not-authorized page**

`apps/admin/app/not-authorized/page.tsx`:

```tsx
import Link from 'next/link';

export default function NotAuthorizedPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md rounded-lg border border-border bg-card p-8 text-card-foreground shadow-sm">
        <h1 className="mb-2 text-xl font-semibold">Not authorized</h1>
        <p className="mb-4 text-sm text-muted-foreground">
          This page is for Goliatt operators. If you are a customer, please use
          the customer portal instead.
        </p>
        <Link href="https://goliatt.co" className="text-sm underline">
          Go to goliatt.co
        </Link>
      </div>
    </main>
  );
}
```

- [ ] **Step 6: Move the dev hello-world content out of the way**

Confirm `apps/admin/app/(operator)/` is empty for now; future tasks add files under it. We can `mkdir -p apps/admin/app/\(operator\)` proactively.

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
mkdir -p 'apps/admin/app/(operator)'
```

- [ ] **Step 7: Verify dev server compiles + redirect works**

Start: `pnpm --filter @odoo-saas/admin dev`
Load http://localhost:3001 — expected: redirects to /licenses, which 404s (no route yet) — that's fine for this task.
Load http://localhost:3001/not-authorized — expected: renders the not-authorized card.

Stop dev server.

- [ ] **Step 8: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/app/layout.tsx apps/admin/app/page.tsx \
        'apps/admin/app/(operator)/layout.tsx' \
        apps/admin/app/not-authorized/page.tsx \
        apps/admin/components/app-shell.tsx
git commit -m "feat(admin): layout shell + sidebar + operator gate + /not-authorized"
```

---

## Task 8: `/licenses` dashboard — list page (read-only)

**Files:**
- Create: `apps/admin/lib/license-status.ts`
- Create: `apps/admin/components/license-status-badge.tsx`
- Create: `apps/admin/components/license-table.tsx`
- Create: `apps/admin/components/license-filters.tsx`
- Create: `apps/admin/app/(operator)/licenses/page.tsx`

- [ ] **Step 1: License status helper**

`apps/admin/lib/license-status.ts`:

```ts
// UI-side status derivation.
//
// packages/api exports `evaluateLicense(row, imageSha256, now)` which
// returns a richer verdict including `image-mismatch`. The UI never has
// a runtime imageSha256 to compare against (the addon supplies it, not
// us), so the UI needs a strict subset: just `active|grace|expired|revoked`.
// Keep this thin helper local rather than mocking imageSha256 into the
// shared evaluator.

export type LicenseStatus = 'active' | 'grace' | 'expired' | 'revoked';

export function deriveLicenseStatus(row: {
  revokedAt: Date | null;
  expiresAt: Date;
  graceUntil: Date;
}, now = new Date()): LicenseStatus {
  if (row.revokedAt) return 'revoked';
  if (row.expiresAt > now) return 'active';
  if (row.graceUntil > now) return 'grace';
  return 'expired';
}
```

- [ ] **Step 2: Status badge component**

`apps/admin/components/license-status-badge.tsx`:

```tsx
import { Badge } from '@/components/ui/badge';

import { deriveLicenseStatus, type LicenseStatus } from '@/lib/license-status';

const VARIANT: Record<LicenseStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  active: 'default',
  grace: 'secondary',
  expired: 'outline',
  revoked: 'destructive',
};

export function LicenseStatusBadge({
  row,
  now,
}: {
  row: { revokedAt: Date | null; expiresAt: Date; graceUntil: Date };
  now?: Date;
}) {
  const status = deriveLicenseStatus(row, now);
  return <Badge variant={VARIANT[status]}>{status}</Badge>;
}
```

- [ ] **Step 3: License filters (client island)**

`apps/admin/components/license-filters.tsx`:

```tsx
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTransition } from 'react';

import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const STATUS_OPTIONS = ['all', 'active', 'grace', 'expired', 'revoked'] as const;

export function LicenseFilters() {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value && value !== 'all') {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    next.delete('cursor'); // reset pagination on filter change
    startTransition(() => router.replace(`/licenses?${next.toString()}`));
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Input
        placeholder="customer ref"
        defaultValue={params.get('customer') ?? ''}
        onBlur={(e) => setParam('customer', e.target.value || null)}
        className="w-56"
      />
      <Input
        placeholder="image sha256 (full)"
        defaultValue={params.get('image') ?? ''}
        onBlur={(e) => setParam('image', e.target.value || null)}
        className="w-72 font-mono text-xs"
      />
      <Select
        defaultValue={params.get('status') ?? 'all'}
        onValueChange={(v) => setParam('status', v)}
      >
        <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
        <SelectContent>
          {STATUS_OPTIONS.map((s) => (
            <SelectItem key={s} value={s}>{s}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
```

- [ ] **Step 4: License table**

`apps/admin/components/license-table.tsx`:

```tsx
import Link from 'next/link';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { LicenseStatusBadge } from './license-status-badge';

type LicenseRow = {
  id: string;
  customerRef: string;
  imageSha256: string;
  expiresAt: Date;
  graceUntil: Date;
  revokedAt: Date | null;
  createdAt: Date;
};

function fmtDate(d: Date | null): string {
  if (!d) return '—';
  return d.toISOString().slice(0, 10);
}

export function LicenseTable({ rows }: { rows: LicenseRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No licenses match these filters.
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Customer</TableHead>
          <TableHead>Image</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Expires</TableHead>
          <TableHead>Grace until</TableHead>
          <TableHead>Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell>
              <Link href={`/licenses/${r.id}`} className="underline">{r.customerRef}</Link>
            </TableCell>
            <TableCell className="font-mono text-xs">{r.imageSha256.slice(0, 12)}…</TableCell>
            <TableCell><LicenseStatusBadge row={r} /></TableCell>
            <TableCell>{fmtDate(r.expiresAt)}</TableCell>
            <TableCell>{fmtDate(r.graceUntil)}</TableCell>
            <TableCell>{fmtDate(r.createdAt)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 5: Dashboard page**

`apps/admin/app/(operator)/licenses/page.tsx`:

```tsx
import Link from 'next/link';

import { Button } from '@/components/ui/button';

import { LicenseFilters } from '@/components/license-filters';
import { LicenseTable } from '@/components/license-table';
import { getServerCaller } from '@/lib/trpc-server';

type Search = {
  customer?: string;
  image?: string;
  status?: 'active' | 'grace' | 'expired' | 'revoked' | 'all';
  cursor?: string;
};

export default async function LicensesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const caller = await getServerCaller();
  const { rows, nextCursor } = await caller.enterpriseLicenses.list({
    customerRef: sp.customer,
    imageSha256: sp.image,
    status: sp.status,
    cursor: sp.cursor,
    limit: 50,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Licenses</h1>
        <Button asChild>
          <Link href="/licenses/new">Mint license</Link>
        </Button>
      </div>
      <LicenseFilters />
      <LicenseTable rows={rows} />
      {nextCursor && (
        <div className="flex justify-end">
          <Button asChild variant="outline">
            <Link
              href={`/licenses?${new URLSearchParams({
                ...(sp.customer ? { customer: sp.customer } : {}),
                ...(sp.image ? { image: sp.image } : {}),
                ...(sp.status ? { status: sp.status } : {}),
                cursor: nextCursor,
              }).toString()}`}
            >
              Next page →
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Verify dev server**

Start: `pnpm --filter @odoo-saas/admin dev`
Sign in as the operator (`user_3DgK5vhEVCA14BeTh3bYyx17A8B`), navigate to `/licenses`.
Expected: page renders, shows "No licenses match these filters" (we have no enterprise licenses yet in prod Neon — that's correct).
Test filter: paste a fake image hash and confirm the URL updates.

Stop dev server.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/lib/license-status.ts \
        apps/admin/components/license-status-badge.tsx \
        apps/admin/components/license-filters.tsx \
        apps/admin/components/license-table.tsx \
        'apps/admin/app/(operator)/licenses/page.tsx'
git commit -m "feat(admin): /licenses dashboard — read-only list + filters + paginate"
```

---

## Task 9: `/licenses/[id]` detail page (read-only)

**Files:**
- Create: `apps/admin/components/license-detail-grid.tsx`
- Create: `apps/admin/app/(operator)/licenses/[id]/page.tsx`

- [ ] **Step 1: Detail grid component**

`apps/admin/components/license-detail-grid.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { LicenseStatusBadge } from './license-status-badge';

type LicenseRow = {
  id: string;
  customerRef: string;
  imageSha256: string;
  expiresAt: Date;
  graceUntil: Date;
  revokedAt: Date | null;
  revokedReason: string | null;
  allowedModules: string[] | null;
  notes: string | null;
  createdAt: Date;
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

export function LicenseDetailGrid({ row }: { row: LicenseRow }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          <span>{row.customerRef}</span>
          <LicenseStatusBadge row={row} />
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-4">
        <Field label="License ID" value={<code className="font-mono text-xs">{row.id}</code>} />
        <Field label="Image SHA256" value={<code className="font-mono text-xs break-all">{row.imageSha256}</code>} />
        <Field label="Expires at" value={row.expiresAt.toISOString()} />
        <Field label="Grace until" value={row.graceUntil.toISOString()} />
        <Field label="Created at" value={row.createdAt.toISOString()} />
        <Field label="Revoked at" value={row.revokedAt ? row.revokedAt.toISOString() : '—'} />
        <Field label="Revoked reason" value={row.revokedReason ?? '—'} />
        <Field
          label="Allowed modules"
          value={row.allowedModules?.length ? row.allowedModules.join(', ') : 'all'}
        />
        <Field label="Notes" value={<pre className="whitespace-pre-wrap text-sm">{row.notes ?? '—'}</pre>} />
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Inline audit table (for this license only)**

Re-use `audit.list` filtered by `targetId`. Create a small wrapper at the bottom of the detail page; no separate component file yet (we'll factor later if we need it elsewhere).

- [ ] **Step 3: Detail page**

`apps/admin/app/(operator)/licenses/[id]/page.tsx`:

```tsx
import { notFound } from 'next/navigation';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { LicenseDetailGrid } from '@/components/license-detail-grid';
import { getServerCaller } from '@/lib/trpc-server';

export default async function LicenseDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const caller = await getServerCaller();
  let row;
  try {
    row = await caller.enterpriseLicenses.get({ id });
  } catch {
    notFound();
  }
  const audit = await caller.audit.list({ targetId: id, targetType: 'license', limit: 50 });

  return (
    <div className="space-y-6">
      <LicenseDetailGrid row={row} />
      <section className="space-y-2">
        <h2 className="text-lg font-medium">Audit trail for this license</h2>
        {audit.rows.length === 0 ? (
          <div className="text-sm text-muted-foreground">No audit entries.</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {audit.rows.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="text-xs text-muted-foreground">{a.ts.toISOString()}</TableCell>
                  <TableCell className="font-mono text-xs">{a.action}</TableCell>
                  <TableCell className="text-xs">{a.actorUserId ?? 'system'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Verify**

Start dev server, navigate to `/licenses/<some-real-uuid>` (or test the 404 path with `/licenses/00000000-0000-0000-0000-000000000000`). Expected: 404 page for unknown id; detail card for a known id.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/components/license-detail-grid.tsx \
        'apps/admin/app/(operator)/licenses/[id]/page.tsx'
git commit -m "feat(admin): /licenses/[id] detail with inline audit trail"
```

---

## Task 10: Bootstrap vitest in `apps/admin`

**Files:**
- Modify: `apps/admin/package.json`
- Create: `apps/admin/vitest.config.ts`
- Create: `apps/admin/test/license-status.test.ts`

- [ ] **Step 1: Install vitest + RTL deps**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
pnpm --filter @odoo-saas/admin add -D vitest @vitest/coverage-v8 @testing-library/react @testing-library/dom jsdom @vitejs/plugin-react
```

- [ ] **Step 2: Add `test` scripts**

In `apps/admin/package.json` scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: Vitest config**

`apps/admin/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['test/**/*.test.ts', 'test/**/*.test.tsx'],
  },
});
```

- [ ] **Step 4: First unit test — deriveLicenseStatus**

`apps/admin/test/license-status.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { deriveLicenseStatus } from '@/lib/license-status';

const NOW = new Date('2026-06-01T00:00:00Z');

describe('deriveLicenseStatus', () => {
  it('active when expires_at in future, not revoked', () => {
    expect(deriveLicenseStatus({
      revokedAt: null,
      expiresAt: new Date('2026-12-31'),
      graceUntil: new Date('2027-01-15'),
    }, NOW)).toBe('active');
  });

  it('grace when expires_at past but grace_until future', () => {
    expect(deriveLicenseStatus({
      revokedAt: null,
      expiresAt: new Date('2026-05-01'),
      graceUntil: new Date('2026-06-15'),
    }, NOW)).toBe('grace');
  });

  it('expired when grace_until past', () => {
    expect(deriveLicenseStatus({
      revokedAt: null,
      expiresAt: new Date('2026-04-01'),
      graceUntil: new Date('2026-05-15'),
    }, NOW)).toBe('expired');
  });

  it('revoked beats anything else', () => {
    expect(deriveLicenseStatus({
      revokedAt: new Date('2026-04-15'),
      expiresAt: new Date('2027-01-01'),
      graceUntil: new Date('2027-01-15'),
    }, NOW)).toBe('revoked');
  });

  it('boundary: expires_at exactly now → grace (not active)', () => {
    expect(deriveLicenseStatus({
      revokedAt: null,
      expiresAt: NOW,
      graceUntil: new Date('2026-06-15'),
    }, NOW)).toBe('grace');
  });

  it('boundary: grace_until exactly now → expired', () => {
    expect(deriveLicenseStatus({
      revokedAt: null,
      expiresAt: new Date('2026-04-01'),
      graceUntil: NOW,
    }, NOW)).toBe('expired');
  });
});
```

- [ ] **Step 5: Run — expect 6 passing**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/admin test`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/package.json apps/admin/vitest.config.ts \
        apps/admin/test/license-status.test.ts pnpm-lock.yaml
git commit -m "test(admin): bootstrap vitest + deriveLicenseStatus unit tests"
```

---

## Task 11: Server actions module (TDD)

**Files:**
- Create: `apps/admin/lib/actions/licenses.ts`
- Create: `apps/admin/test/actions-licenses.test.ts`

- [ ] **Step 1: Write failing tests first**

`apps/admin/test/actions-licenses.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockGetServerCaller = vi.fn();
vi.mock('@/lib/trpc-server', () => ({ getServerCaller: () => mockGetServerCaller() }));
vi.mock('@/lib/auth/operator-gate', () => ({
  requireOperator: vi.fn(async () => ({ userId: 'user_op', user: {} })),
}));
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));
vi.mock('next/navigation', () => ({ redirect: vi.fn() }));

import {
  mintLicenseAction,
  revokeLicenseAction,
  restoreLicenseAction,
} from '@/lib/actions/licenses';

beforeEach(() => mockGetServerCaller.mockReset());

describe('mintLicenseAction', () => {
  it('returns ok on success', async () => {
    const issued = { id: 'lic_new', customerRef: 'acme' };
    mockGetServerCaller.mockResolvedValue({
      enterpriseLicenses: { issue: vi.fn(async () => issued) },
    });
    const result = await mintLicenseAction({
      customerRef: 'acme',
      imageSha256: 'a'.repeat(64),
      termDays: 365,
      graceDays: 14,
      notes: '',
    });
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.data.id).toBe('lic_new');
  });

  it('returns VALIDATION on bad input', async () => {
    const result = await mintLicenseAction({
      customerRef: '',
      imageSha256: 'not-hex',
      termDays: 365,
      graceDays: 14,
      notes: '',
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe('VALIDATION');
  });
});

describe('revokeLicenseAction', () => {
  it('returns ok on success', async () => {
    mockGetServerCaller.mockResolvedValue({
      enterpriseLicenses: { revoke: vi.fn(async () => ({ id: 'lic_a', revokedAt: new Date() })) },
    });
    const result = await revokeLicenseAction({ id: 'lic_a', reason: 'non-payment' });
    expect(result.ok).toBe(true);
  });

  it('returns CONFLICT on already-revoked', async () => {
    mockGetServerCaller.mockResolvedValue({
      enterpriseLicenses: {
        revoke: vi.fn(async () => { throw new Error('already revoked'); }),
      },
    });
    const result = await revokeLicenseAction({ id: 'lic_a', reason: 'r' });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(['CONFLICT', 'INTERNAL']).toContain(result.error.code);
  });
});

describe('restoreLicenseAction', () => {
  it('returns ok on success', async () => {
    mockGetServerCaller.mockResolvedValue({
      enterpriseLicenses: { restore: vi.fn(async () => ({ id: 'lic_a' })) },
    });
    const result = await restoreLicenseAction({ id: 'lic_a' });
    expect(result.ok).toBe(true);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane && pnpm --filter @odoo-saas/admin test actions-licenses`
Expected: FAIL — module `@/lib/actions/licenses` not found.

- [ ] **Step 3: Implement the actions module**

`apps/admin/lib/actions/licenses.ts`:

```ts
'use server';

import { revalidatePath } from 'next/cache';
import { z } from 'zod';

import { requireOperator } from '@/lib/auth/operator-gate';
import { getServerCaller } from '@/lib/trpc-server';

type ActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: { code: ErrorCode; message: string; fieldErrors?: Record<string, string> } };

type ErrorCode = 'UNAUTHORIZED' | 'VALIDATION' | 'CONFLICT' | 'INTERNAL' | 'NETWORK';

const mintSchema = z.object({
  customerRef: z.string().min(1).max(120),
  imageSha256: z.string().regex(/^[0-9a-f]{64}$/),
  termDays: z.number().int().min(1).max(3650).default(365),
  graceDays: z.number().int().min(0).max(365).default(14),
  notes: z.string().max(2000).optional(),
  allowedModules: z.array(z.string()).optional(),
});

export async function mintLicenseAction(input: z.input<typeof mintSchema>): Promise<ActionResult<{ id: string }>> {
  await requireOperator();
  const parsed = mintSchema.safeParse(input);
  if (!parsed.success) {
    const fieldErrors: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      fieldErrors[issue.path.join('.')] = issue.message;
    }
    return { ok: false, error: { code: 'VALIDATION', message: 'invalid input', fieldErrors } };
  }
  try {
    const caller = await getServerCaller();
    const data = await caller.enterpriseLicenses.issue(parsed.data);
    revalidatePath('/licenses');
    return { ok: true, data: { id: data.id } };
  } catch (err) {
    return mapError(err);
  }
}

const revokeSchema = z.object({
  id: z.string().uuid(),
  reason: z.string().min(1).max(500),
});

export async function revokeLicenseAction(input: z.input<typeof revokeSchema>): Promise<ActionResult<void>> {
  await requireOperator();
  const parsed = revokeSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: { code: 'VALIDATION', message: 'invalid input' } };
  }
  try {
    const caller = await getServerCaller();
    await caller.enterpriseLicenses.revoke(parsed.data);
    revalidatePath('/licenses');
    revalidatePath(`/licenses/${parsed.data.id}`);
    return { ok: true, data: undefined };
  } catch (err) {
    return mapError(err);
  }
}

const restoreSchema = z.object({ id: z.string().uuid() });

export async function restoreLicenseAction(input: z.input<typeof restoreSchema>): Promise<ActionResult<void>> {
  await requireOperator();
  const parsed = restoreSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, error: { code: 'VALIDATION', message: 'invalid input' } };
  }
  try {
    const caller = await getServerCaller();
    await caller.enterpriseLicenses.restore(parsed.data);
    revalidatePath('/licenses');
    revalidatePath(`/licenses/${parsed.data.id}`);
    return { ok: true, data: undefined };
  } catch (err) {
    return mapError(err);
  }
}

function mapError(err: unknown): { ok: false; error: { code: ErrorCode; message: string } } {
  const msg = err instanceof Error ? err.message : 'unknown error';
  if (/already revoked|conflict|already exists/i.test(msg)) {
    return { ok: false, error: { code: 'CONFLICT', message: msg } };
  }
  return { ok: false, error: { code: 'INTERNAL', message: msg } };
}
```

- [ ] **Step 4: Run — expect PASS**

Run: `pnpm --filter @odoo-saas/admin test actions-licenses`
Expected: 5 passing.

- [ ] **Step 5: Add adversarial tests (covers spec §7 adversarial bullet)**

Append to `apps/admin/test/actions-licenses.test.ts`:

```ts
import { requireOperator } from '@/lib/auth/operator-gate';

describe('adversarial — defense-in-depth on actions', () => {
  it('mint with 10 KB notes succeeds (no length limit on text)', async () => {
    mockGetServerCaller.mockResolvedValue({
      enterpriseLicenses: { issue: vi.fn(async (i) => ({ id: 'lic_big', ...i })) },
    });
    const longNotes = 'x'.repeat(2000); // schema cap = 2000
    const result = await mintLicenseAction({
      customerRef: 'acme',
      imageSha256: 'a'.repeat(64),
      termDays: 365,
      graceDays: 14,
      notes: longNotes,
    });
    expect(result.ok).toBe(true);
  });

  it('mint rejects notes longer than schema cap', async () => {
    const result = await mintLicenseAction({
      customerRef: 'acme',
      imageSha256: 'a'.repeat(64),
      termDays: 365,
      graceDays: 14,
      notes: 'x'.repeat(2001),
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe('VALIDATION');
  });

  it('revoke with non-uuid id is VALIDATION (not INTERNAL)', async () => {
    const result = await revokeLicenseAction({ id: "'; DROP TABLE--", reason: 'r' });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe('VALIDATION');
  });

  it('non-operator: requireOperator throws → action never reaches tRPC', async () => {
    vi.mocked(requireOperator).mockRejectedValueOnce(new Error('redirect to /not-authorized'));
    const callerSpy = vi.fn();
    mockGetServerCaller.mockResolvedValue({ enterpriseLicenses: { revoke: callerSpy } });
    await expect(revokeLicenseAction({ id: '00000000-0000-0000-0000-000000000000', reason: 'r' }))
      .rejects.toThrow(/redirect/);
    expect(callerSpy).not.toHaveBeenCalled();
  });
});
```

Run: `pnpm --filter @odoo-saas/admin test actions-licenses`
Expected: 9 passing (5 from step 1 + 4 adversarial).

- [ ] **Step 6: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/lib/actions/licenses.ts apps/admin/test/actions-licenses.test.ts
git commit -m "feat(admin): server actions for mint/revoke/restore license + tests

Includes adversarial cases per spec §7: long-notes acceptance + over-
cap rejection, malformed-uuid rejection (VALIDATION not INTERNAL), and
proof that requireOperator() fires before the tRPC caller is even
constructed."
```

---

## Task 12: `/licenses/new` mint form

**Files:**
- Create: `apps/admin/components/mint-license-form.tsx`
- Create: `apps/admin/app/(operator)/licenses/new/page.tsx`

- [ ] **Step 1: Mint form (client island)**

`apps/admin/components/mint-license-form.tsx`:

```tsx
'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { mintLicenseAction } from '@/lib/actions/licenses';

export function MintLicenseForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function onSubmit(formData: FormData) {
    const input = {
      customerRef: String(formData.get('customerRef') ?? ''),
      imageSha256: String(formData.get('imageSha256') ?? ''),
      termDays: Number(formData.get('termDays') ?? 365),
      graceDays: Number(formData.get('graceDays') ?? 14),
      notes: String(formData.get('notes') ?? ''),
    };
    const result = await mintLicenseAction(input);
    if (result.ok) {
      toast.success('License minted');
      router.push(`/licenses/${result.data.id}`);
    } else if (result.error.code === 'VALIDATION') {
      setErrors(result.error.fieldErrors ?? {});
      toast.error('Fix the highlighted fields');
    } else {
      toast.error(`${result.error.code}: ${result.error.message}`);
    }
  }

  return (
    <form
      action={(fd) => startTransition(() => onSubmit(fd))}
      className="grid max-w-2xl gap-4"
    >
      <div className="grid gap-2">
        <Label htmlFor="customerRef">Customer reference</Label>
        <Input id="customerRef" name="customerRef" required placeholder="acme@example.com" />
        {errors.customerRef && <span className="text-xs text-destructive">{errors.customerRef}</span>}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="imageSha256">Image SHA256 (64 hex chars)</Label>
        <Input id="imageSha256" name="imageSha256" required className="font-mono text-xs" />
        {errors.imageSha256 && <span className="text-xs text-destructive">{errors.imageSha256}</span>}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label htmlFor="termDays">Term (days)</Label>
          <Input id="termDays" name="termDays" type="number" defaultValue={365} min={1} max={3650} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="graceDays">Grace (days)</Label>
          <Input id="graceDays" name="graceDays" type="number" defaultValue={14} min={0} max={365} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="notes">Notes (operator-only)</Label>
        <Textarea id="notes" name="notes" rows={4} />
      </div>
      <div>
        <Button type="submit" disabled={pending}>{pending ? 'Minting…' : 'Mint license'}</Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Mint page**

`apps/admin/app/(operator)/licenses/new/page.tsx`:

```tsx
import { MintLicenseForm } from '@/components/mint-license-form';

export default function NewLicensePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Mint license</h1>
      <p className="text-sm text-muted-foreground max-w-prose">
        Issues a new license bound to a customer reference and a specific image
        digest. Pre-fill the digest with the SHA256 from the customer's pinned
        enterprise-v* GHCR tag.
      </p>
      <MintLicenseForm />
    </div>
  );
}
```

- [ ] **Step 3: Verify dev server**

Start dev server, navigate to `/licenses/new`. Submit with empty fields — expected: VALIDATION errors highlight inline. Submit with valid customer + a fake 64-hex digest — should successfully mint (unless DB constraint catches it) and redirect to the detail page.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/components/mint-license-form.tsx \
        'apps/admin/app/(operator)/licenses/new/page.tsx'
git commit -m "feat(admin): /licenses/new mint form with field-level errors"
```

---

## Task 13: Revoke dialog + Restore button on detail page

**Files:**
- Create: `apps/admin/components/revoke-dialog.tsx`
- Create: `apps/admin/components/restore-button.tsx`
- Modify: `apps/admin/app/(operator)/licenses/[id]/page.tsx`

- [ ] **Step 1: Revoke dialog**

`apps/admin/components/revoke-dialog.tsx`:

```tsx
'use client';

import { useState, useTransition } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { revokeLicenseAction } from '@/lib/actions/licenses';

export function RevokeDialog({ licenseId }: { licenseId: string }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [pending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      const result = await revokeLicenseAction({ id: licenseId, reason });
      if (result.ok) {
        toast.success('License revoked');
        setOpen(false);
      } else {
        toast.error(`${result.error.code}: ${result.error.message}`);
      }
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive">Revoke</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke this license?</DialogTitle>
          <DialogDescription>
            The customer's saas_license_gate addon will see the change within an
            hour and flip write-heavy models to read-only (or fully invalid past
            grace_until).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 py-2">
          <Label htmlFor="reason">Reason (required, free-form)</Label>
          <Textarea
            id="reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="Non-payment, 90 days past due"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>Cancel</Button>
          <Button variant="destructive" onClick={submit} disabled={pending || !reason.trim()}>
            {pending ? 'Revoking…' : 'Confirm revoke'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Restore button**

`apps/admin/components/restore-button.tsx`:

```tsx
'use client';

import { useTransition } from 'react';
import { toast } from 'sonner';

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';

import { restoreLicenseAction } from '@/lib/actions/licenses';

export function RestoreButton({ licenseId }: { licenseId: string }) {
  const [pending, startTransition] = useTransition();

  function run() {
    startTransition(async () => {
      const result = await restoreLicenseAction({ id: licenseId });
      if (result.ok) toast.success('License restored');
      else toast.error(`${result.error.code}: ${result.error.message}`);
    });
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline">Restore</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Restore this license?</AlertDialogTitle>
          <AlertDialogDescription>
            Clears revoked_at. The customer's addon will re-validate within an
            hour and restore write access (assuming expires_at is still in the
            future, otherwise the license falls into grace or expired).
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={run} disabled={pending}>
            {pending ? 'Restoring…' : 'Confirm restore'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 3: Wire into detail page**

In `apps/admin/app/(operator)/licenses/[id]/page.tsx`, add an action bar above the `LicenseDetailGrid`. Modify the return to:

```tsx
import { RevokeDialog } from '@/components/revoke-dialog';
import { RestoreButton } from '@/components/restore-button';

// ... inside the component, after the row is fetched:

return (
  <div className="space-y-6">
    <div className="flex items-center justify-end gap-2">
      {row.revokedAt ? <RestoreButton licenseId={row.id} /> : <RevokeDialog licenseId={row.id} />}
    </div>
    <LicenseDetailGrid row={row} />
    {/* audit trail section stays unchanged */}
    ...
  </div>
);
```

- [ ] **Step 4: Verify**

Start dev server, navigate to a license detail page. Click Revoke, enter a reason, confirm — expected: toast appears, page reloads, status badge flips to "revoked", action bar now shows Restore. Click Restore, confirm — page flips back to active.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/components/revoke-dialog.tsx \
        apps/admin/components/restore-button.tsx \
        'apps/admin/app/(operator)/licenses/[id]/page.tsx'
git commit -m "feat(admin): revoke dialog + restore button on license detail"
```

---

## Task 14: `/audit` generic viewer

**Files:**
- Create: `apps/admin/components/audit-filters.tsx`
- Create: `apps/admin/components/audit-table.tsx`
- Create: `apps/admin/components/audit-payload-modal.tsx`
- Create: `apps/admin/app/(operator)/audit/page.tsx`

- [ ] **Step 1: Audit filters (client)**

`apps/admin/components/audit-filters.tsx`:

```tsx
'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTransition } from 'react';

import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const NAMESPACES = ['all', 'license', 'tenant', 'backup', 'email'] as const;

export function AuditFilters() {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value && value !== 'all') next.set(key, value); else next.delete(key);
    next.delete('cursor');
    startTransition(() => router.replace(`/audit?${next.toString()}`));
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        defaultValue={params.get('namespace') ?? 'all'}
        onValueChange={(v) => setParam('namespace', v)}
      >
        <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
        <SelectContent>
          {NAMESPACES.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
        </SelectContent>
      </Select>
      <Input
        placeholder="target id"
        defaultValue={params.get('targetId') ?? ''}
        onBlur={(e) => setParam('targetId', e.target.value || null)}
        className="w-56 font-mono text-xs"
      />
      <Input
        placeholder="actor (user_xxx)"
        defaultValue={params.get('actor') ?? ''}
        onBlur={(e) => setParam('actor', e.target.value || null)}
        className="w-56 font-mono text-xs"
      />
    </div>
  );
}
```

- [ ] **Step 2: Audit payload modal**

`apps/admin/components/audit-payload-modal.tsx`:

```tsx
'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export function AuditPayloadModal({ payload }: { payload: unknown }) {
  const [open, setOpen] = useState(false);
  if (payload === null || payload === undefined) return <span className="text-muted-foreground">—</span>;
  const pretty = JSON.stringify(payload, null, 2);
  const preview = pretty.length > 80 ? pretty.slice(0, 77) + '…' : pretty;
  return (
    <>
      <Button variant="ghost" size="sm" className="font-mono text-xs" onClick={() => setOpen(true)}>
        {preview}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader><DialogTitle>Audit payload</DialogTitle></DialogHeader>
          <pre className="max-h-[60vh] overflow-auto rounded bg-muted p-3 text-xs">{pretty}</pre>
        </DialogContent>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 3: Audit table**

`apps/admin/components/audit-table.tsx`:

```tsx
import Link from 'next/link';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { AuditPayloadModal } from './audit-payload-modal';

type AuditRow = {
  id: string;
  ts: Date;
  actorUserId: string | null;
  action: string;
  targetType: string | null;
  targetId: string | null;
  payload: unknown;
};

export function AuditTable({ rows }: { rows: AuditRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        No audit entries match these filters.
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>When</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Target</TableHead>
          <TableHead>Payload</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell className="text-xs text-muted-foreground">{r.ts.toISOString()}</TableCell>
            <TableCell className="font-mono text-xs">{r.action}</TableCell>
            <TableCell className="text-xs">{r.actorUserId ?? 'system'}</TableCell>
            <TableCell className="font-mono text-xs">
              {r.targetType === 'license' && r.targetId ? (
                <Link href={`/licenses/${r.targetId}`} className="underline">{r.targetType}/{r.targetId.slice(0, 8)}…</Link>
              ) : r.targetType && r.targetId ? (
                `${r.targetType}/${r.targetId.slice(0, 8)}…`
              ) : '—'}
            </TableCell>
            <TableCell><AuditPayloadModal payload={r.payload} /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: Audit page**

`apps/admin/app/(operator)/audit/page.tsx`:

```tsx
import Link from 'next/link';

import { Button } from '@/components/ui/button';

import { AuditFilters } from '@/components/audit-filters';
import { AuditTable } from '@/components/audit-table';
import { getServerCaller } from '@/lib/trpc-server';

type Search = {
  namespace?: 'license' | 'tenant' | 'backup' | 'email' | 'all';
  targetId?: string;
  actor?: string;
  cursor?: string;
};

export default async function AuditPage({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const caller = await getServerCaller();
  const { rows, nextCursor } = await caller.audit.list({
    actionPrefix: sp.namespace && sp.namespace !== 'all' ? sp.namespace : undefined,
    targetId: sp.targetId,
    actor: sp.actor,
    cursor: sp.cursor,
    limit: 50,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Audit log</h1>
      <AuditFilters />
      <AuditTable rows={rows} />
      {nextCursor && (
        <div className="flex justify-end">
          <Button asChild variant="outline">
            <Link
              href={`/audit?${new URLSearchParams({
                ...(sp.namespace ? { namespace: sp.namespace } : {}),
                ...(sp.targetId ? { targetId: sp.targetId } : {}),
                ...(sp.actor ? { actor: sp.actor } : {}),
                cursor: nextCursor,
              }).toString()}`}
            >
              Next page →
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verify**

Start dev server, navigate to `/audit`. Expected: table renders with whatever rows are in `audit_log`. Filter by namespace=license; rows should narrow.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/components/audit-filters.tsx \
        apps/admin/components/audit-table.tsx \
        apps/admin/components/audit-payload-modal.tsx \
        'apps/admin/app/(operator)/audit/page.tsx'
git commit -m "feat(admin): /audit generic viewer with filters + payload modal"
```

---

## Task 15: `/signing-key` probe page

**Files:**
- Create: `apps/admin/lib/actions/signing-key.ts`
- Create: `apps/admin/components/signing-key-probe-panel.tsx`
- Create: `apps/admin/app/(operator)/signing-key/page.tsx`

- [ ] **Step 1: Probe server action**

`apps/admin/lib/actions/signing-key.ts`:

```ts
'use server';

import crypto from 'node:crypto';

import { requireOperator } from '@/lib/auth/operator-gate';

type ProbeResult =
  | { ok: true; status: 'PASS'; httpStatus: number; body: string }
  | { ok: false; reason: 'KEY_UNSET' | 'HMAC_MISMATCH' | 'NETWORK' | 'UNEXPECTED'; httpStatus: number; body: string };

const AUTHORITY_URL = process.env.LICENSE_AUTHORITY_URL ?? 'https://odoo-saas-admin.vercel.app';
const SECRET = process.env.SAAS_PROVISIONING_SECRET;

export async function probeSigningKeyAction(): Promise<ProbeResult> {
  await requireOperator();
  if (!SECRET) {
    return {
      ok: false,
      reason: 'UNEXPECTED',
      httpStatus: 0,
      body: 'SAAS_PROVISIONING_SECRET not configured on this admin runtime.',
    };
  }
  const ts = Math.floor(Date.now() / 1000);
  const body = JSON.stringify({
    license_id: '00000000-0000-0000-0000-000000000000',
    image_sha256: 'deadbeef',
    machine_id: 'admin-probe-signing-key',
    timestamp: ts,
  });
  const sig = crypto.createHmac('sha256', SECRET).update(`${ts}.${body}`).digest('hex');
  let response: Response;
  try {
    response = await fetch(`${AUTHORITY_URL}/api/internal/license/check`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-saas-timestamp': String(ts),
        'x-saas-signature': `sha256=${sig}`,
      },
      body,
    });
  } catch (e) {
    return { ok: false, reason: 'NETWORK', httpStatus: 0, body: String(e) };
  }
  const text = await response.text();
  if (response.status === 200 || response.status === 404) {
    return { ok: true, status: 'PASS', httpStatus: response.status, body: text };
  }
  if (response.status === 503 && /license-signing-key-unset/.test(text)) {
    return { ok: false, reason: 'KEY_UNSET', httpStatus: 503, body: text };
  }
  if (response.status === 401) {
    return { ok: false, reason: 'HMAC_MISMATCH', httpStatus: 401, body: text };
  }
  return { ok: false, reason: 'UNEXPECTED', httpStatus: response.status, body: text };
}
```

- [ ] **Step 2: Probe panel (client island)**

`apps/admin/components/signing-key-probe-panel.tsx`:

```tsx
'use client';

import { useState, useTransition } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { probeSigningKeyAction } from '@/lib/actions/signing-key';

type ProbeResult = Awaited<ReturnType<typeof probeSigningKeyAction>>;

export function SigningKeyProbePanel() {
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [pending, startTransition] = useTransition();

  function run() {
    startTransition(async () => {
      setResult(await probeSigningKeyAction());
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Probe /api/internal/license/check</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button onClick={run} disabled={pending}>{pending ? 'Probing…' : 'Run probe'}</Button>
        {result && (
          <div className="space-y-2 rounded-md border border-border p-3 text-sm">
            <div>
              {result.ok ? (
                <span className="font-medium text-green-700">PASS</span>
              ) : (
                <span className="font-medium text-destructive">FAIL — {result.reason}</span>
              )}
              {' '}(HTTP {result.httpStatus})
            </div>
            <pre className="max-h-64 overflow-auto rounded bg-muted p-2 text-xs">{result.body}</pre>
            {!result.ok && result.reason === 'KEY_UNSET' && (
              <p className="text-xs text-muted-foreground">
                LICENSE_SIGNING_PRIVATE_KEY_B64 is set but didn't reach the
                runtime. Re-deploy admin and retry.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Page**

`apps/admin/app/(operator)/signing-key/page.tsx`:

```tsx
import { SigningKeyProbePanel } from '@/components/signing-key-probe-panel';

export default function SigningKeyPage() {
  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">Signing key probe</h1>
      <p className="text-sm text-muted-foreground">
        Smoke-tests that LICENSE_SIGNING_PRIVATE_KEY_B64 is loaded on the admin
        runtime. Calls /api/internal/license/check with a sentinel HMAC envelope.
        Equivalent to <code className="font-mono text-xs">license-cli.sh verify-signing-key</code>.
      </p>
      <SigningKeyProbePanel />
    </div>
  );
}
```

- [ ] **Step 4: Verify**

Start dev server, navigate to `/signing-key`, click Run probe. Expected: PASS (HTTP 200 or 404) since we set LICENSE_SIGNING_PRIVATE_KEY_B64 in the previous session.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/lib/actions/signing-key.ts \
        apps/admin/components/signing-key-probe-panel.tsx \
        'apps/admin/app/(operator)/signing-key/page.tsx'
git commit -m "feat(admin): /signing-key probe page"
```

---

## Task 16: Playwright E2E setup + 5 specs

**Files:**
- Modify: `apps/admin/package.json`
- Create: `apps/admin/playwright.config.ts`
- Create: `apps/admin/e2e/operator-can-access.spec.ts`
- Create: `apps/admin/e2e/non-operator-bounced.spec.ts`
- Create: `apps/admin/e2e/mint.spec.ts`
- Create: `apps/admin/e2e/revoke-restore.spec.ts`
- Create: `apps/admin/e2e/signing-key.spec.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
pnpm --filter @odoo-saas/admin add -D @playwright/test
pnpm --filter @odoo-saas/admin exec playwright install chromium --with-deps
```

- [ ] **Step 2: Add e2e scripts**

`apps/admin/package.json` scripts:

```json
"e2e": "playwright test",
"e2e:ui": "playwright test --ui"
```

- [ ] **Step 3: Playwright config**

`apps/admin/playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3001',
    trace: 'on-first-retry',
    headless: true,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
```

- [ ] **Step 4: Auth-helper for Clerk test users**

The control plane uses Clerk; E2E needs a non-interactive way to sign in. Use Clerk's testing-token utility, gated by env vars:

`apps/admin/e2e/auth-helper.ts`:

```ts
import type { Page } from '@playwright/test';

const OPERATOR_TOKEN = process.env.E2E_OPERATOR_CLERK_TOKEN;
const NON_OPERATOR_TOKEN = process.env.E2E_NON_OPERATOR_CLERK_TOKEN;

export async function signInAsOperator(page: Page) {
  if (!OPERATOR_TOKEN) throw new Error('E2E_OPERATOR_CLERK_TOKEN not set');
  await page.goto('/');
  await page.evaluate((t) => { window.localStorage.setItem('__clerk_db_jwt', t); }, OPERATOR_TOKEN);
}
export async function signInAsNonOperator(page: Page) {
  if (!NON_OPERATOR_TOKEN) throw new Error('E2E_NON_OPERATOR_CLERK_TOKEN not set');
  await page.goto('/');
  await page.evaluate((t) => { window.localStorage.setItem('__clerk_db_jwt', t); }, NON_OPERATOR_TOKEN);
}
```

(See open question #3 in the spec — the precise Clerk testing-token mechanism may need a different approach; this helper is the integration point.)

- [ ] **Step 5: Spec — operator can access**

`apps/admin/e2e/operator-can-access.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { signInAsOperator } from './auth-helper';

test('operator lands on /licenses and sees the dashboard', async ({ page }) => {
  await signInAsOperator(page);
  await page.goto('/licenses');
  await expect(page.getByRole('heading', { name: 'Licenses' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Mint license/i })).toBeVisible();
});
```

- [ ] **Step 6: Spec — non-operator bounced**

`apps/admin/e2e/non-operator-bounced.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { signInAsNonOperator } from './auth-helper';

test('non-operator hits /licenses, ends up on /not-authorized', async ({ page }) => {
  await signInAsNonOperator(page);
  await page.goto('/licenses');
  await expect(page).toHaveURL(/\/not-authorized$/);
  await expect(page.getByRole('heading', { name: 'Not authorized' })).toBeVisible();
});
```

- [ ] **Step 7: Spec — mint**

`apps/admin/e2e/mint.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { signInAsOperator } from './auth-helper';

const FAKE_DIGEST = 'a'.repeat(64);
const CUSTOMER_REF = `e2e-test-${Date.now()}@example.com`;

test('operator mints a new license and lands on its detail page', async ({ page }) => {
  await signInAsOperator(page);
  await page.goto('/licenses/new');
  await page.getByLabel('Customer reference').fill(CUSTOMER_REF);
  await page.getByLabel('Image SHA256').fill(FAKE_DIGEST);
  await page.getByRole('button', { name: /Mint license/i }).click();
  await expect(page).toHaveURL(/\/licenses\/[0-9a-f-]+$/);
  await expect(page.getByText(CUSTOMER_REF)).toBeVisible();
});
```

- [ ] **Step 8: Spec — revoke + restore round-trip**

`apps/admin/e2e/revoke-restore.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { signInAsOperator } from './auth-helper';

const FAKE_DIGEST = 'b'.repeat(64);
const CUSTOMER_REF = `e2e-rr-${Date.now()}@example.com`;

test('operator revokes then restores a license; status badge round-trips', async ({ page }) => {
  await signInAsOperator(page);
  await page.goto('/licenses/new');
  await page.getByLabel('Customer reference').fill(CUSTOMER_REF);
  await page.getByLabel('Image SHA256').fill(FAKE_DIGEST);
  await page.getByRole('button', { name: /Mint license/i }).click();
  await expect(page).toHaveURL(/\/licenses\/[0-9a-f-]+$/);

  // Revoke
  await page.getByRole('button', { name: 'Revoke' }).click();
  await page.getByLabel('Reason').fill('e2e revoke');
  await page.getByRole('button', { name: 'Confirm revoke' }).click();
  await expect(page.locator('[data-slot="badge"]:has-text("revoked")')).toBeVisible();

  // Restore
  await page.getByRole('button', { name: 'Restore' }).click();
  await page.getByRole('button', { name: 'Confirm restore' }).click();
  await expect(page.locator('[data-slot="badge"]:has-text("active")')).toBeVisible();
});
```

- [ ] **Step 9: Spec — signing-key probe**

`apps/admin/e2e/signing-key.spec.ts`:

```ts
import { test, expect } from '@playwright/test';
import { signInAsOperator } from './auth-helper';

test('signing-key probe returns PASS', async ({ page }) => {
  await signInAsOperator(page);
  await page.goto('/signing-key');
  await page.getByRole('button', { name: 'Run probe' }).click();
  await expect(page.getByText('PASS')).toBeVisible({ timeout: 15_000 });
});
```

- [ ] **Step 10: Commit (without running)**

We commit the specs without running them; the run requires Clerk test users to be provisioned (open question #3 in the spec, deferred). The CI workflow in Task 17 will wire this up.

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add apps/admin/package.json apps/admin/playwright.config.ts \
        apps/admin/e2e/ pnpm-lock.yaml
git commit -m "test(admin): Playwright e2e specs (5 scenarios) + auth helper

Run requires E2E_OPERATOR_CLERK_TOKEN and E2E_NON_OPERATOR_CLERK_TOKEN
env vars set to Clerk DB JWTs; provisioning a test Clerk org is the
v1 follow-up (spec §10 open question 3)."
```

---

## Task 17: CI workflow — `test-control-plane` job

**Files:**
- Create: `Odoo-control-plane/.github/workflows/test-control-plane.yml`

(Data plane and control plane are separate repos with their own GitHub Actions. This file goes in the CONTROL plane repo.)

- [ ] **Step 1: Create the workflow file**

In the control plane repo, create `.github/workflows/test-control-plane.yml`:

```yaml
name: Control plane CI

on:
  pull_request:
    paths:
      - 'apps/admin/**'
      - 'apps/portal/**'
      - 'packages/api/**'
      - 'packages/db/**'
      - 'packages/backup/**'
      - 'packages/infra/**'
      - 'packages/workflows/**'
      - '.github/workflows/test-control-plane.yml'
  push:
    branches: [main]

concurrency:
  group: control-plane-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: Lint + typecheck + unit tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @odoo-saas/api lint
      - run: pnpm --filter @odoo-saas/admin lint
      - run: pnpm --filter @odoo-saas/api typecheck
      - run: pnpm --filter @odoo-saas/admin typecheck
      - run: pnpm --filter @odoo-saas/api test
      - run: pnpm --filter @odoo-saas/admin test

  e2e:
    name: Playwright (chromium)
    runs-on: ubuntu-latest
    needs: [test]
    if: github.event_name == 'pull_request'
    env:
      E2E_BASE_URL: ${{ secrets.E2E_PREVIEW_URL }}
      E2E_OPERATOR_CLERK_TOKEN: ${{ secrets.E2E_OPERATOR_CLERK_TOKEN }}
      E2E_NON_OPERATOR_CLERK_TOKEN: ${{ secrets.E2E_NON_OPERATOR_CLERK_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @odoo-saas/admin exec playwright install chromium --with-deps
      - name: Wait for Vercel preview deployment to be Ready
        run: |
          for i in {1..30}; do
            if curl -fsS "${E2E_BASE_URL}/" >/dev/null; then echo "ready"; exit 0; fi
            sleep 10
          done
          echo "preview never came up" >&2
          exit 1
        if: env.E2E_BASE_URL != ''
      - run: pnpm --filter @odoo-saas/admin e2e
        if: env.E2E_BASE_URL != '' && env.E2E_OPERATOR_CLERK_TOKEN != ''
      - name: Skip notice
        run: echo "E2E skipped — E2E_BASE_URL or E2E_OPERATOR_CLERK_TOKEN secret not set"
        if: env.E2E_BASE_URL == '' || env.E2E_OPERATOR_CLERK_TOKEN == ''
```

- [ ] **Step 2: Commit**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo-control-plane
git add .github/workflows/test-control-plane.yml
git commit -m "ci: control-plane lint/typecheck/test workflow + Playwright gate"
```

---

## Task 18: Integration tests (ephemeral Neon — DEFERRED)

The spec §7 promised integration tests against an ephemeral Neon branch. Setting up Neon branch lifecycle in CI requires a Neon API token + branch-naming convention that the operator hasn't decided. **Defer to a follow-up plan** to keep this plan shippable. Open question for the user: provision `NEON_API_KEY` + write a `branch-create + branch-delete` GitHub action, or skip and rely on unit + E2E for v1.

For v1, mark this task complete with: "deferred per scope choice; tracked in spec §10 implicit follow-up."

- [ ] **Step 1: Note the deferral in the spec**

Edit `docs/superpowers/specs/2026-05-17-license-management-ui-design.md` §10 to add:

```markdown
6. **Integration-test layer against ephemeral Neon branches is deferred from v1 ship.** Unit tests cover the action contracts; Playwright E2E covers the user-visible behavior. Reconsider after the first real customer onboarding to see if the unit-only gap caused any production issue. **Open until incident-driven justification.**
```

- [ ] **Step 2: Commit the deferral note**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo
git add docs/superpowers/specs/2026-05-17-license-management-ui-design.md
git commit -m "spec(operator-ui): defer ephemeral-Neon integration tests from v1"
```

(Data plane repo, since the spec file lives in the data plane.)

---

## Task 19: Final cleanup + spec status to Accepted

**Files:**
- Modify: `docs/superpowers/specs/2026-05-17-license-management-ui-design.md`

- [ ] **Step 1: Bump spec status**

Replace `**Status:** Draft` with `**Status:** Accepted (implemented)` in the spec header.

- [ ] **Step 2: Quick smoke walk-through in the deployed admin app**

After all PRs have shipped to production:

- Sign in as the operator on https://odoo-saas-admin.vercel.app
- Verify `/licenses` renders (table empty unless any enterprise licenses have been minted)
- Mint a test license against a fake digest, confirm detail page renders
- Revoke it with a reason, refresh, confirm badge flips
- Restore, refresh, confirm badge flips back
- `/audit` shows the 3 audit entries from the round-trip
- `/signing-key` returns PASS
- Sign out, sign in as a non-operator, confirm `/licenses` redirects to `/not-authorized`

- [ ] **Step 3: Commit spec status bump**

```bash
cd /Volumes/SATECHI2TB/userfolder/Odoo
git add docs/superpowers/specs/2026-05-17-license-management-ui-design.md
git commit -m "spec(operator-ui): mark Accepted (implemented)"
```

---

## Done.

After all 19 tasks ship: operator drives license management from the browser; `license-cli.sh` stays usable as a power-user fallback; future tenant CRUD / plan CRUD / backup-catalog UIs slot into the same layout shell, the same shadcn primitives, the same Server Components + Server Actions pattern.

Total estimated diff (excluding shadcn primitive source files): ~1100 LOC of new code, ~30 LOC modified in `enterprise-licenses.ts`. ~10 new commits, 19 PR-sized cohesive chunks if you want to ship each task as its own PR, OR batch into 4–5 larger PRs (one per rollout group from spec §8).
