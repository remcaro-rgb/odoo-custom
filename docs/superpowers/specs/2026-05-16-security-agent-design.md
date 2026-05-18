# Security Agent — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** autonomous security review and remediation agent. Runs on a 12-hour cron schedule plus immediate runs on critical CVEs. Posts pre-review security reports on Implementation Agent PRs. Maintains the masking allow-list and sensitive-topics list. Sits on the v7 portable runtime.

---

## 1. Goal

Find and propose fixes for security issues in `custom-addons/**` continuously and at low marginal cost. Specifically:

- Daily dependency vulnerability scan (`pip-audit`, `npm audit`).
- 12-hourly static-analysis scan (`bandit` + custom Odoo rules).
- Daily record-rule audit (new/changed models must have appropriate `ir.rule` entries).
- Daily secrets-in-code scan (`gitleaks`).
- 12-hourly tenancy-boundary audit (file-only — never auto-PR).
- Pre-review security reports on every Implementation Agent PR before `awaiting-human-review`.
- Maintain `infra/agentlab/mask-allowlist.yml` and `infra/agentlab/sensitive-topics.yml` (proposes additions; humans approve).

---

## 2. Non-goals

- **Architectural security decisions.** Those are spec-driven and human-approved.
- **Incident response.** When a real incident happens, humans run the incident; the agent supplies forensic context but doesn't act.
- **Code quality / performance.** Other agents own those.
- **Auto-merging anything.** Even trivial CVE bumps require human approval.
- **Modifying `saas_tenant_gate/security/**` without security-lead approval.** The agent can propose; humans must sign.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────┐
│ agents/agents/security/                          │
│   core.py            ← orchestration             │
│   loops/                                         │
│     dependency.py    ← pip-audit + npm audit     │
│     bandit.py        ← static analysis           │
│     odoo_rules.py    ← Odoo-specific patterns    │
│     record_rules.py  ← ir.rule audit             │
│     gitleaks.py      ← secrets-in-code           │
│     tenancy.py       ← cross-tenant leak check   │
│   pre_review.py      ← post security report     │
│   masking.py         ← maintain allow-list       │
│   sensitive_topics.py ← maintain list            │
│   fixer.py           ← LLM-driven small fixes    │
└────────────┬─────────────────────────────────────┘
             │ uses ports
             ▼
   LLMProvider · Repo · IssueTracker · Notifier ·
   ComputeEnv · KnowledgeBase · SecretStore ·
   EventBus · Logger · ArtifactStore
```

---

## 4. Tenancy impact

Critical. The agent's primary job is preserving tenancy boundaries. Specifically:

- The **tenancy loop** scans for `self.env['model'].sudo()` patterns in `saas_*` addons that could escape tenant isolation. **File-only** — never auto-PR. Filed as an issue with `tenancy-boundary` label; routes to security-leads.
- The **record-rule loop** ensures every new model in `custom-addons/` has at least one `ir.rule` scoping it (by `company_id` or `user_id`) before it can reach `main`.
- The **masking allow-list** controls which columns in agentlab snapshots are unmasked — directly affects whether agent-lab work can leak real data.

The agent does NOT have any read access to real production data. It works against agentlab (which has masked snapshots).

---

## 5. Loops in detail

### 5.1 Dependency loop

Cadence: daily. Critical CVE (CVSS ≥ 8.0) triggers immediate run.

```
1. pip-audit on agents Python deps + Odoo runtime deps
2. npm audit on web/static/ deps
3. For each finding:
     - severity ≥ 8.0 → hotfix flow (see §11.3 of main plan)
     - severity ≥ 6.0 → normal PR with bump
     - severity < 6.0 → file as issue, batch weekly
4. fixer.bump_dep(package, target_version)
5. Verify with agentlab (do tests still pass?)
6. Open PR with title '[agent:security] CVE-YYYY-NNNN: bump <pkg>'
```

### 5.2 Static analysis loop

Cadence: every 12h.

```
1. Run bandit -ll over custom-addons/
2. Custom Odoo rules (in odoo_rules.py):
     - Controllers with auth='public' that access env[...].sudo()
     - SQL string concatenation in env.cr.execute
     - Sensitive menus/actions missing groups=
     - read_group/search without domain on user-controlled inputs
3. For each finding:
     - Confident fix (B608 SQL injection with known-safe rewrite) → PR
     - Ambiguous fix → file as issue with proposed approach
4. Severity tag: critical / high / medium / low
```

### 5.3 Record-rule audit loop

Cadence: daily.

```
1. git diff main..main~7  on models/ directories
2. For each new/changed model:
     - parse to find ir.model.access entries
     - parse to find ir.rule entries
     - assert at least one rule scopes by company_id or user_id
     - if missing: file issue with `tenancy-boundary` label
3. The Implementation Agent's pre-review checks for this issue label
   on the PR's models — refuses to mark PR ready for human review until clear.
```

### 5.4 Secrets-in-code loop

Cadence: daily.

```
1. gitleaks scan on the full repo + recent 30 commits
2. Custom regex for:
     - Odoo master passwords (ADMIN_PASSWORD heuristic)
     - S3 keys (AKIA, ...)
     - Telemetry HMACs
3. Any finding → PR to remove + file an issue tagged `incident-followup`
4. Page security-leads immediately on critical findings
```

### 5.5 Tenancy-boundary audit loop (file-only)

Cadence: every 12h.

```
1. Static scan for patterns:
     - .sudo() in saas_* addons
     - Cross-DB queries (env.cr.execute on multiple dbnames)
     - Caching that doesn't key by db.dbname
     - Raw SQL referencing tables without WHERE on company_id/db
2. For each finding:
     - Run LLM analyzer: is this a real risk or false positive?
     - Confidence ≥ 0.6 → file issue with `tenancy-boundary` label
     - Confidence < 0.6 → log, no issue
3. Issues route to security-leads CODEOWNERS
4. NO auto-PR. These are decision-grade.
```

### 5.6 Pre-review security report

Trigger: `pull_request.labeled` with `reporter-approved` on `agent/spec-*`.

```
1. Diff against base
2. Run on the diff:
     - bandit + Odoo custom rules
     - record-rule presence check on touched models
     - gitleaks
     - sudo()/cross-tenant pattern detection
3. Post markdown comment on the PR:

     ### Security Agent pre-review
     - Bandit findings: 0
     - Custom Odoo rules: 0
     - Record rules on new models: ✓ all present
     - Tenancy-boundary patterns: ⚠ 1 found (see below; non-blocking)
     - Secrets scan: clean

     Detail:
     - file.py:42 — env['x'].sudo() inside a public controller. Verify this is intentional.

   Reviewer must react to this comment before approving (rubber-stamp guard).
```

### 5.7 Masking allow-list maintenance

Quarterly (manual trigger or cron):

```
1. Inspect tenant-DB schema for new columns added since last quarter
2. For each new column:
     - LLM judgement: is this PII?
     - If yes → flag as 'should-remain-masked'
     - If no → propose adding to allow-list
3. Open PR against `infra/agentlab/mask-allowlist.yml` with proposed additions
4. security-leads CODEOWNERS approval required
```

### 5.8 Sensitive-topics maintenance

Same quarterly cadence:

```
1. Inspect chatbot conversations from last quarter (gateway events)
2. Cluster on topics
3. For new clusters that look sensitive (LLM judgement):
     - Propose adding regex/embedding to sensitive-topics.yml
4. Open PR; security-leads approval required
```

---

## 6. Data model

```sql
CREATE TABLE security_findings (
    id              bigserial primary key,
    loop            text not null,        -- dependency | bandit | odoo-rules | record-rules | gitleaks | tenancy | pre-review
    cvss            numeric(3,1),         -- CVSS where applicable
    severity        text not null,        -- critical | high | medium | low | info
    target_path     text,
    target_line     int,
    description     text,
    state           text not null,        -- pending | issue-filed | pr-open | merged | dismissed
    issue_number    int,
    pr_number       int,
    confidence      numeric(4,3),
    cost_usd        numeric(8,4),
    created_at      timestamptz default now()
);
```

---

## 7. API surface

CLI:
```
agents run security [--loop dependency|bandit|odoo-rules|record-rules|gitleaks|tenancy|all]
agents run security --pre-review --pr 1501
agents run security --hotfix --cve CVE-2026-12345
agents security findings --severity high
agents security maintain --allowlist
agents security maintain --sensitive-topics
```

Webhooks: `pull_request.labeled` (pre-review). Cron: `0 */12 * * *`. Plus: GitHub Advisory webhook for immediate critical CVE response.

---

## 8. Security model

- **Bot identity:** `security-agent-bot@<your-domain>`. Signed commits.
- **Scope:**
  - Write: `custom-addons/**` (except `saas_*/security/**` — co-sign required), `custom-addons/**/security/**`, tests.
  - Read: all.
  - Propose-only (via PR against): `infra/agentlab/mask-allowlist.yml`, `infra/agentlab/sensitive-topics.yml`.
- **Forbidden:** `.github/workflows/**`, `infra/**` (except the two files above), `Dockerfile`, `agents/**/CHARTER.md`.
- **Tenancy loop is issue-only.** No auto-PR ever.
- **Spend cap:** $60/week (higher than other agents — security work justifies it).

---

## 9. Test plan

### Unit
- `loops/bandit.py`: assert all known patterns trigger.
- `loops/odoo_rules.py`: 30 fixture files with deliberate violations → 30 findings.
- `loops/record_rules.py`: fixture model without rule → flagged; with rule → clean.
- `loops/tenancy.py`: 20 fixture violations → 20 findings.

### Integration
- Full dependency loop with a planted CVE → PR opened with correct bump.
- Full pre-review on a fixture PR with planted issues → all caught.

### Adversarial
- Inject sudo() with intentional bypass → tenancy loop catches.
- Inject secret in commit body (not diff) → gitleaks catches.
- LLM tries to dismiss a real finding via crafted comment → human review required (no auto-dismiss).

---

## 10. Rollout plan

Phase 9 of v7 (weeks 16–18, before optimisation agent). Security must be online by end of week 18 because pre-review reports are required for the Implementation Agent's human-review gate.

Sub-phases:
- **9a (week 16):** dependency + bandit loops.
- **9b (week 17):** record-rules + gitleaks + Odoo custom rules.
- **9c (week 18):** tenancy loop + pre-review reports.
- **9d (week 18):** maintenance loops (allow-list + sensitive topics).

### Canary
1. Shadow mode (1 week, findings logged, no PRs).
2. Live, dependency only, 1 PR cap.
3. All loops live, 3 PR cap, after 2 weeks clean.

### Rollback
Kill switch. Critical CVE response continues even when other loops are paused (separate workflow with its own kill).

---

## 11. Observability

- Per-finding row in `security_findings`.
- Dashboard: findings/day by loop, MTTR (issue file → PR merge), CVE backlog age, tenancy-loop findings open count.
- Alerts:
  - Critical CVE (CVSS ≥ 8) found → page on-call immediately.
  - Tenancy-loop finding open > 14d → page security-leads.
  - Secrets-in-code finding → page on-call immediately.
  - Spend > 80% of cap.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| False positive flood | Findings dashboard | Tune rules; loop pauses if FP rate > 50% |
| LLM dismisses a real bug | Sample audit by security-leads | Loop disabled for that addon until reviewed |
| Tenancy-loop alarm fatigue | Findings dashboard | Quarterly threshold tuning |
| Critical CVE during off-hours | Auto-page | Hotfix flow is well-rehearsed (rollback rehearsal weekly) |
| Bot tries to "fix" a finding incorrectly | Verifier + tests catch | Loop logs and continues |
| Allow-list PR mistakenly unmasks PII | CODEOWNERS catches at review | Hard requirement: 2 security-lead approvals on allow-list PRs |

---

## 13. Open questions

1. Should we run Snyk in addition to pip-audit? Costs money but covers more.
2. Should the tenancy-loop's confidence threshold be 0.6, or higher? Lower captures more real risks but increases false-positive rate.
3. Are quarterly maintenance runs enough for the allow-list, or should we re-audit monthly?
4. Should pre-review reports also run on human-authored PRs? Adds value; doubles compute.
