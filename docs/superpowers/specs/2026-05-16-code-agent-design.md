# Code Agent — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** autonomous code-quality improvement agent. Runs on a 6-hour cron schedule. Picks tasks from its own backlog of code-quality findings. Sits on the v7 portable runtime.

---

## 1. Goal

Improve code quality and developer ergonomics on `custom-addons/**` without taking developer time. Specifically:

- Detect duplicated code across addons; propose extraction into shared helpers (typically `club_core` for the club_* family).
- Find addons with < 50% statement coverage; backfill tests for the most-used model methods.
- Find `__manifest__.py` files missing `description`, `author`, `license`, or with stale `depends`; fix them.
- Generate `README.md` for addons that don't have one (synthesised from manifest + models + views).
- Find unreferenced methods, fields, templates, and assets (dead code); propose removal.
- Post **pre-review code-quality reports** on every Implementation Agent PR before it enters `awaiting-human-review` (per Implementation Agent design §16).

---

## 2. Non-goals

- **Feature work.** That's the Implementation Agent's job. Code Agent never adds new behaviour.
- **Security fixes.** Security Agent owns these — Code Agent stays out of `security/` directories.
- **Performance optimisation.** Optimization Agent owns that.
- **Breaking changes.** Refactors must be behaviour-preserving. If they can't be, agent files an issue instead of opening a PR.
- **Anything in `saas_*` addons without security-agent co-sign.** Control-plane code requires extra scrutiny.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────┐
│ agents/agents/code/                              │
│   core.py          ← orchestration               │
│   backlog.py       ← scan codebase, build queue  │
│   loops/                                         │
│     test_backfill.py                             │
│     refactor.py                                  │
│     manifest_hygiene.py                          │
│     readme_gen.py                                │
│     dead_code.py                                 │
│   pre_review.py    ← post quality report on PRs  │
│   coder.py         ← LLM-driven code generation  │
│   verifier.py      ← run Gate-1 on agentlab      │
└────────────┬─────────────────────────────────────┘
             │ uses ports
             ▼
   LLMProvider · Repo · IssueTracker · Notifier ·
   ComputeEnv · KnowledgeBase · SecretStore ·
   EventBus · Logger · ArtifactStore
```

---

## 4. Tenancy impact

None directly. The agent's PRs flow into `main` and ride the wave system. Pre-review reports it posts on Implementation Agent PRs don't bypass any tenancy gates.

---

## 5. Loops in detail

### 5.1 Test backfill loop

Cadence: every 6h.

```
1. backlog.scan_coverage():
     - run pytest --cov on agentlab (one off, against latest main)
     - emit addon -> coverage% map
2. picks = addons where coverage < 50%, sorted ascending by % then by usage
3. for picked in picks[:1]:  # one addon per run
     a. Read addon's models, views, recent commits
     b. coder.write_tests_for(addon=picked):
          - pick 2–4 most-used model methods (by call-site grep)
          - draft pytest tests with realistic fixtures
     c. verifier.run(agentlab, addon=picked):
          - run new tests; assert they pass
          - assert coverage went up
     d. Open PR with title '[agent:code] test backfill: <addon>'
```

Max +400 LOC per PR (agent-guardrails enforces).

### 5.2 Refactor loop (duplicate code)

Cadence: every 6h.

```
1. backlog.scan_duplicates():
     - run jscpd over custom-addons/club_*
     - emit (file_a, file_b, lines, similarity) tuples
2. picks = duplicates with similarity ≥ 0.85 and ≥ 15 lines, grouped by intent
3. for picked in picks[:1]:
     a. coder.propose_extraction(picked):
          - read both sites; understand the variation
          - draft a shared helper (typically in club_core/utils.py)
          - rewrite both sites to use it
     b. verifier.run(addons_touched)
     c. Open PR
```

### 5.3 Manifest hygiene loop

Cadence: daily.

```
1. backlog.scan_manifests():
     - for each custom-addons/<addon>/__manifest__.py:
         parse; check fields {description, author, license, depends, version}
         flag missing fields, fix wherever unambiguous (e.g. license == 'AGPL-3')
2. for picked in picks[:3]:    # several easy fixes per run
     a. coder.fix_manifest(picked):
          - generate description from README or first docstring
          - fill in author from git log (most-frequent committer)
          - flag depends inconsistencies (e.g. depends on something not installed
            in the addon's deps tree)
     b. verifier.run()
     c. Open PR (one PR per addon, easier to review)
```

### 5.4 README generation loop

Cadence: weekly.

```
1. backlog.scan_readmes():
     - for each custom-addons/<addon>:
         if no README.md or README.md < 20 lines: pick
2. for picked in picks[:2]:
     a. coder.draft_readme(picked):
          - read manifest + top-level models + main views
          - produce: overview, what it does, models created, views/actions exposed,
            dependencies, installation notes, examples
     b. Open PR (docs-only changes are low-risk)
```

### 5.5 Dead-code loop

Cadence: weekly.

```
1. backlog.scan_dead_code():
     - vulture or rope to find unreferenced methods / fields / templates
     - cross-check XML records that reference the symbols (Odoo-specific)
2. for picked in picks[:1]:
     a. Mark candidates with a `[possible-dead]` comment in code (no removal yet)
     b. If a candidate has been marked for ≥ 30 days and no human un-marked it:
          coder.remove_dead(candidate)
     c. Open PR
```

Conservative — never auto-removes immediately. Two-step process gives humans time to object.

### 5.6 Pre-review report on Implementation Agent PRs

Trigger: `pull_request.labeled` with `reporter-approved` on `agent/spec-*`.

```
1. Read the PR diff
2. Run on the diff (not against full main):
     - jscpd (duplicate detection)
     - vulture (dead code)
     - coverage delta (vs base)
     - lint (ruff + black --check)
3. coder.synthesise_report() → markdown comment posted on the PR:

     ### Code Agent pre-review report
     - Coverage: +1.2% (good)
     - Duplicate-code findings: 0
     - Dead-code findings: 0
     - Lint: clean
     - Refactor suggestions: 2 (non-blocking, see below)

   Reviewer must react to this comment before approving (per main plan §10
   rubber-stamping mitigation).
```

---

## 6. Data model

```sql
CREATE TABLE code_agent_findings (
    id              bigserial primary key,
    loop            text not null,       -- test-backfill | refactor | manifest | readme | dead-code | pre-review
    target          text not null,       -- addon name or file path
    description     text,
    severity        text,                -- info | suggestion | required
    state           text not null,       -- pending | pr-open | merged | dismissed
    pr_number       int,
    cost_usd        numeric(8,4),
    created_at      timestamptz default now()
);
```

---

## 7. API surface

CLI commands:
```
agents run code [--loop test-backfill|refactor|manifest|readme|dead-code|all]
agents run code --pre-review --pr 1501
agents code findings --addon <name>
agents code dismiss --finding-id <id>
```

Webhooks: `pull_request.labeled` (for pre-review trigger). Cron: `0 */6 * * *` for backlog runs.

---

## 8. Security model

- **Bot identity:** `code-agent-bot@<your-domain>`. Signed commits. Excluded from human-commit ping.
- **Scope:**
  - Write: `custom-addons/**` (except `custom-addons/saas_*/security/**`), `docs/**`, test files.
  - Read: everything.
- **Forbidden:**
  - `.github/`, `infra/`, `Dockerfile`, `agents/**/CHARTER.md`.
  - `saas_tenant_gate/security/**`, `saas_provisioning_gateway/security/**` (requires security-agent co-sign label).
- **Guardrails:** the runtime's `agent-guardrails.yml` (≤ 400 LOC, signed commits, test count must not shrink).
- **Spend cap:** $40/week.

---

## 9. Test plan

### Unit
- Each loop's `scan_*()` over a fixture repo → emits expected findings.
- `coder.write_tests_for()` on a known addon → tests pass on agentlab.
- `coder.propose_extraction()` on known-duplicate fixture → produces idempotent refactor.

### Integration
- Full test-backfill run on a fixture with < 50% coverage → coverage goes up; tests pass; PR opened.
- Pre-review report on a fixture PR with intentional duplicate code → flagged correctly.

### Adversarial
- Refactor that subtly changes behaviour → verifier catches via Gate 1 + existing tests.
- Test-backfill that writes flaky tests → CI marks flaky after retry; agent's PR is closed by human.

---

## 10. Rollout plan

Phase 9 of the v7 master roadmap (weeks 16–17). Sub-phases:

- **9a:** manifest hygiene + README generation (lowest risk).
- **9b:** test backfill.
- **9c:** refactor (duplicate extraction).
- **9d:** dead code (with the 30-day mark-and-wait).
- **9e:** pre-review reports on Implementation Agent PRs.

### Canary
1. Shadow mode (no PRs opened) for 1 week.
2. Live, 1 open PR cap.
3. Raise to 3-PR cap after 2 weeks clean.

### Rollback
Kill switch via `AGENTS_ENABLED`. Backlog persists; resumes on re-enable.

---

## 11. Observability

- Per-run logs tagged `agent=code`, `loop`, `target`, `pr`.
- Dashboard: findings/day, PRs opened/merged, PR merge rate (target ≥ 50%), false-positive rate (target < 30%), cost/week.
- Alerts: merge rate drops below 30% (signal: review backlog or bad output); spend 80%+ of cap.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Test-backfill produces flaky tests | CI re-run detects; merge rate drops | Loop pauses for human review |
| Refactor changes behaviour subtly | Existing tests + Gate 1 catch | PR fails CI; loop logs the failure pattern |
| Manifest fix wrong (e.g. wrong license) | Reviewer rejects | Loop ingests rejection signal; reduces auto-fix scope |
| Dead-code removal hits used-via-XML | XML grep step + 30-day wait | Mark-and-wait gives humans time to un-mark |
| Pre-review report wrong | Reviewer comments back | Loop tunes; quarterly classifier retraining |
| Spend cap hit | Cost tracker | Pause; humans triage backlog |

---

## 13. Open questions

1. Should we treat `co_*` accounting addons as more sensitive (Colombian regulatory) and require additional review?
2. Mark-and-wait period for dead-code — 30 days right, or shorter (7 days) for clearly unreferenced code?
3. Should pre-review reports also run on human-authored PRs (not just agent PRs)? Adds value but doubles compute.
