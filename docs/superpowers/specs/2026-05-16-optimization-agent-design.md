# Optimization Agent — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** autonomous performance and resource-usage improvement agent. Runs daily. Reads `pg_stat_statements`, Fly/Railway metrics, and `ir.cron` runtime stats to find optimisations. Sits on the v7 portable runtime.

---

## 1. Goal

Surface and fix performance + resource problems before they become incidents. Specifically:

- Find slow Postgres queries (> 500ms) and propose indexes or query rewrites.
- Find `@api.depends` chains that recompute on every save and propose `store=True` or batching.
- Find N+1 patterns (loops over recordsets that trigger one query per record).
- Track Dockerfile layer sizes weekly; propose consolidation (issue-only since Dockerfile is restricted).
- Track `ir.cron` jobs that consistently exceed their interval; propose splitting or backgrounding.
- Track Fly/Railway worker pressure (CPU > 70% or memory > 80% sustained); propose worker-count changes (issue-only).

---

## 2. Non-goals

- **Premature optimisation.** Loops only fire on real measured problems, not hypothetical.
- **Code style refactoring.** Code Agent's territory.
- **Security improvements.** Security Agent's territory.
- **Schema migrations beyond indexes.** Indexes are additive and safe; broader migrations need spec-driven work.
- **Dockerfile edits.** Issue-only because Dockerfile is restricted to security-leads.
- **Worker-count autotuning.** Recommendations only; humans deploy.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────┐
│ agents/agents/optimization/                      │
│   core.py            ← orchestration             │
│   loops/                                         │
│     slow_query.py    ← pg_stat_statements        │
│     computed_field.py← static analysis           │
│     n_plus_one.py    ← instrumented agentlab run │
│     image_size.py    ← Dockerfile analysis       │
│     cron_tuning.py   ← ir.cron stats             │
│     worker_pressure.py ← Fly/Railway metrics     │
│   fixer.py           ← propose change + verify   │
│   benchmark.py       ← before/after measurement  │
└────────────┬─────────────────────────────────────┘
             │ uses ports
             ▼
   LLMProvider · Repo · IssueTracker · Notifier ·
   ComputeEnv · KnowledgeBase · SecretStore ·
   EventBus · Logger · ArtifactStore
```

---

## 4. Tenancy impact

The agent reads aggregated metrics, never raw tenant data. Index proposals are schema-level and apply uniformly (in line with the trunk-based-with-waves rollout model). Computed-field changes propagate to all tenants but are behaviour-preserving by definition (just faster).

The agent's instrumented runs happen on agentlab (against masked data) — never against real tenants.

---

## 5. Loops in detail

### 5.1 Slow query loop

Cadence: daily.

```
1. Connect to agentlab Postgres (read-only)
2. SELECT * FROM pg_stat_statements WHERE mean_exec_time > 500
   ORDER BY total_exec_time DESC LIMIT 50
3. For top 5 (deduped by query pattern):
     a. EXPLAIN ANALYZE against agentlab
     b. fixer.propose():
          - missing index? → propose CREATE INDEX (migration file)
          - inefficient query? → propose rewrite (Python/ORM)
          - JOIN-heavy? → consider materialised view
     c. benchmark.run(before, after) on agentlab
     d. Assert after.mean_exec_time < 0.5 × before.mean_exec_time
     e. Open PR with title '[agent:optimization] perf: <table>/<addon>'
        + benchmark numbers in PR body
```

### 5.2 Computed-field loop

Cadence: every 12h.

```
1. Parse all custom-addons/<addon>/models/*.py for fields.* with compute=
2. Build dep graph: which compute methods chain via @api.depends?
3. For each chain:
     - chain length ≥ 3 OR depends includes many2many → candidate
4. For each candidate:
     a. Measure recompute cost (instrumented agentlab run)
     b. If average recompute > 50ms:
          - fixer.propose() — usually store=True with appropriate triggers
          - benchmark before/after
     c. Open PR if benchmark improves ≥ 20%
```

### 5.3 N+1 loop

Cadence: weekly.

```
1. Run canonical workflows on agentlab with query logging:
     - invoice posting
     - POS sale
     - aged-receivable report
     - club_pos checkout
2. For each workflow, parse query log:
     - find loops of identical queries with different parameter values
     - confidence ≥ 0.8 → N+1 candidate
3. fixer.propose():
     - batch read with .read([ids])
     - use prefetch
     - use model.browse(ids) instead of N model.browse(id)
4. benchmark.run()
5. Open PR if query count drops ≥ 50%
```

### 5.4 Image-size loop

Cadence: weekly. Issue-only (Dockerfile restricted).

```
1. docker build the current Dockerfile; export layer-size table
2. Compare to last week's snapshot
3. Find layers that grew > 50 MB OR layers candidate for consolidation
4. File issue '[agent:optimization] Dockerfile: <layer> grew <delta>'
   with recommendation. Routes to security-leads (who own Dockerfile).
```

### 5.5 Cron-tuning loop

Cadence: daily.

```
1. Query ir.cron_run history from agentlab (recent 7 days)
2. For each cron:
     - compute median, p95 actual interval vs configured interval
     - if p95 > 1.5 × configured: candidate
3. fixer.propose():
     - split the job (multiple smaller crons)
     - increase concurrency
     - background via a queue model
4. Open PR if proposal is mechanical
```

### 5.6 Worker-pressure loop

Cadence: daily. Issue-only.

```
1. Pull Fly + Railway metrics (CPU, memory, request latency) for last 24h
2. For each pool (Odoo workers):
     - if sustained CPU > 70% for ≥ 1h: file issue suggesting worker scale-up
     - if memory > 80% for ≥ 1h: same
3. Routes to prod-deployers.
```

---

## 6. Data model

```sql
CREATE TABLE optimization_findings (
    id              bigserial primary key,
    loop            text not null,         -- slow-query | computed-field | n-plus-one | image-size | cron | worker
    target          text,                  -- table / addon / cron / pool
    metric          text,                  -- the measurement that triggered
    before_value    numeric,
    after_value     numeric,               -- post-fix benchmark, if applicable
    improvement_pct numeric,
    state           text not null,         -- pending | pr-open | merged | dismissed | issue-only
    pr_number       int,
    cost_usd        numeric(8,4),
    created_at      timestamptz default now()
);
```

---

## 7. API surface

CLI:
```
agents run optimization [--loop slow-query|computed-field|n-plus-one|image-size|cron|worker|all]
agents optimization findings
agents optimization benchmark --target <table-or-addon>
```

Cron: `0 4 * * *` (daily 04:00 UTC, after agentlab snapshot is fresh).

---

## 8. Security model

- **Bot identity:** `optimization-agent-bot@<your-domain>`.
- **Scope:**
  - Write: `custom-addons/**` (indexes, computed fields, batch reads), `custom-addons/**/migrations/**`.
  - Read: agentlab Postgres (read-only via dedicated user), Fly + Railway metrics APIs.
- **Forbidden:** `Dockerfile` (issue-only), `infra/**`, `.github/workflows/**`, `agents/**/CHARTER.md`.
- **Issue-only loops:** image-size, worker-pressure.
- **Spend cap:** $30/week.

---

## 9. Test plan

### Unit
- `slow_query.parse_explain()` on 20 fixture plans → correct hot-spot identification.
- `computed_field.build_dep_graph()` → correct chains.
- `n_plus_one.detect()` on instrumented logs → correct flagging.
- `benchmark.run()` → reproducible numbers on a fixed dataset.

### Integration
- Inject a slow query on agentlab → loop catches; index proposed; benchmark improves.
- Inject N+1 in a fixture workflow → loop catches; batch read proposed.

### Adversarial
- Index proposal that breaks an existing query plan → benchmark catches; PR fails.
- Optimisation that's actually slower under load → benchmark catches.

---

## 10. Rollout plan

Phase 9 of v7 (week 19). Last of the improvement agents. Goes after Code and Security agents because:
- Pre-review reports from Code/Security are already in place.
- Optimization's PRs benefit from being reviewed against the same quality bar.

Sub-phases:
- **9a (week 19):** slow-query + computed-field (highest-value, lowest-risk).
- **9b (week 19):** N+1 + cron-tuning.
- **9c (week 19):** issue-only loops (image-size, worker-pressure).

### Canary
1. Shadow (1 week).
2. Live, 1 PR cap.
3. 3 PR cap after 2 weeks clean.

---

## 11. Observability

- Per-finding row in `optimization_findings` with benchmark numbers.
- Dashboard: improvements/week, average improvement %, merge rate, false-positive rate, cost/week.
- Alerts: benchmark regressions detected (a proposal made things worse); spend cap.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Proposed index slows other queries | EXPLAIN ANALYZE on representative queries | Bench catches before PR; auto-rejects |
| store=True breaks computed correctness | Tests fail | PR fails CI; loop logs |
| Benchmark non-deterministic | Multiple runs; agent requires ≥ 3 consistent runs before reporting | Stops proposing if variance too high |
| Cron split changes ordering semantics | Test against fixture | If test fails, fall back to issue-only |
| Image-size recommendation actually breaks build | (Issue-only — humans verify) | n/a |

---

## 13. Open questions

1. Should the slow-query loop also consider total_exec_time (impact) or just mean_exec_time? Currently both.
2. N+1 instrumentation runs on agentlab — should we also instrument staging once per week for higher fidelity?
3. Cron tuning is sensitive — should this be issue-only too, with humans always reviewing?
4. Should we ship a `--no-llm` mode for the deterministic loops (slow-query index proposals) to cut cost?
