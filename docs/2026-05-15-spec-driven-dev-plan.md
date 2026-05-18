# Spec-Driven Development, Multi-Environment CI/CD, and AI Agents — Plan v8

**Date:** 2026-05-16 · **Revision:** v8 (Phase 1 foundation shipped; design specs complete for every agent + every component)
**Author:** Manu (drafted with Claude)
**Status:** Draft for team review · **Phase 1 artefacts ready to merge**
**Scope:** Odoo 19 multi-tenant SaaS (Railway + Fly), single `main` branch with per-client config/data, **six AI agents** (5 engineering + 1 customer-facing) running on a **vendor-agnostic ports-and-adapters runtime**, per-spec ephemeral preview environments, three-stage pipeline.

---

## Changelog

**v8 (this revision) — designs complete + Phase 1 foundation shipped**

Concrete artefacts produced in this round (all under the workspace folder):

**Phase 1 foundation:**
- `docs/superpowers/specs/_TEMPLATE-design.md`, `_TEMPLATE-fix.md`
- `docs/superpowers/plans/_TEMPLATE.md`
- `docs/adr/README.md` + ADRs 0001 (trunk-based-with-waves), 0002 (cross-platform parity), 0003 (Better Stack log drain)
- `.github/CODEOWNERS` with team-based ownership for `infra/`, `saas_*`, agent charters, ADRs, runbooks
- `.github/PULL_REQUEST_TEMPLATE.md` with the v6 5-item CODEOWNERS checklist
- `.github/workflows/spec-required.yml` — enforces §2.6 of this plan
- `.github/workflows/agent-guardrails.yml` — enforces all 12 hard rules per agent (≤400 LOC, no infra edits, signed commits, test count must not shrink, spec-correction prefix audit, kill switch via `AGENTS_ENABLED` repo variable)
- `.github/workflows/promote-to-prod.yml` — full workflow per the promote/rollback spec
- `.github/workflows/rollback-prod.yml` — with paste-back confirmation
- `.github/workflows/preview-cleanup.yml` — nightly destruction of stale preview envs
- `.github/workflows/spec-quality.yml` — template completeness + tenancy-impact + open-questions checks on Spec Generator output

**Complete design-spec layer (all under `docs/superpowers/specs/`):**
- Six agents: Spec Generator, Implementation, Code, Security, Optimization, Support Triage.
- Three infrastructure pieces: Agentlab environment, promote-to-prod + rollback + hotfix, Observability stack.
- One data piece: Per-tenant migration queue.
- Two foundational designs: Portable agent runtime, Implementation Agent infographic.

**Runtime skeleton (under `agents/`):**
- `pyproject.toml` with per-adapter optional deps
- `Dockerfile` (multi-stage, slim, signed-ready)
- 10 port ABCs as Python Protocols: LLMProvider, Repo, IssueTracker, Notifier, SecretStore, ArtifactStore, ComputeEnv, KnowledgeBase, EventBus, Logger
- `bootstrap.py` with adapter wiring + production allow-list enforcement
- `cli.py` with `run`, `iterate`, `handle-commit`, `config validate`, `test-adapter`, `preview destroy` subcommands
- `config.py` with YAML + per-env overrides + `AGENTS_*` env-var precedence
- Reference adapters: `secrets_envvar`, `logger_stdjson`, `llm_litellm`
- Test scaffolding: `tests/test_config.py`, `tests/contract/test_logger.py`, contract-test README

**v7 — portable agent runtime**
- **All six agents now sit on a hexagonal runtime.** Agent core logic depends only on ports (`LLMProvider`, `Repo`, `IssueTracker`, `Notifier`, `SecretStore`, `ArtifactStore`, `ComputeEnv`, `KnowledgeBase`, `EventBus`, `Logger`); adapters bind to vendors.
- **One OCI image** (`odoo-saas-agents:<version>`) runs every agent on every CI platform — GitHub Actions, GitLab CI, Argo, Kubernetes Job, local cron.
- **LiteLLM** as the default `LLMProvider` adapter; first-party direct adapters for Claude, OpenAI, Gemini, Ollama. Per-agent model defaults configurable; fallback chains on outage.
- **Default day-one bindings unchanged** from v6 (GitHub + Claude + Slack + Fly + pgvector). Swapping any one is now a config change, not a rewrite.
- **New roadmap phase 6** for the runtime + adapter library (weeks 9–10); other agent phases renumbered 7–10. Total 10 phases.
- New design spec: [`docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md`](superpowers/specs/2026-05-16-portable-agent-runtime-design.md).
- New "lock-in risk" table identifies the vendors we depend on and the migration cost for each.

**v6 — open-question lock-ins + customer-facing Support Triage Agent**
- Q1 ✅ **Tiered soak time.** 24h for `risk:low|medium`; 72h for `risk:high`. Auto-detected from PR touched paths; CODEOWNERS can override.
- Q2 ✅ **Three waves.** Within-wave granularity via per-tenant `maintenance_window` already in §8.
- Q3 ✅ **Masking allow-list owner:** security agent proposes; `security-leads` CODEOWNERS group approves. File at `infra/agentlab/mask-allowlist.yml`.
- Q4 ✅ **Language policy:** English for specs/plans/code/ADRs; bilingual auto-translation for issue comments to non-English reporters; customer-facing replies in reporter's language.
- Q5 ✅ **`prod-deployers`:** start with 2 (Manu + lead dev). N=1 normal promote; N=2 hotfix and rollback. Add security lead when hired.
- Q6 ✅ **Log drain:** Better Stack to start. ADR-0003 documents. Migrate to self-hosted Loki on Fly past ~100 GB/month.
- Q7 ✅ **Slack `/spec` / `/confirm` / `/approve`:** Zapier during Phases 6–7; replace with a Fly-hosted bot in Phase 8+.
- Q8 ✅ **Hotfix `spec-exempt` admin:** same `prod-deployers` group; N=2 raises the bar enough.
- Q9 ✅ **Preview access:** one-time password default; `access_level: oauth-required` spec metadata triggers OAuth proxy for sensitive features. Build OAuth proxy in a deferred Phase 9 if pulled.
- Q10 ✅ **Reporter identity (extended):** support three channels:
  1. GitHub user — comments natively in the issue.
  2. External via support email — auto-creates issue, email-relay forwarder.
  3. **In-app support chatbot** — new addon `saas_support_chatbot` + gateway. See full design at [`docs/superpowers/specs/2026-05-16-support-triage-agent-design.md`](superpowers/specs/2026-05-16-support-triage-agent-design.md). New 6th agent: **Support Triage Agent** (§5.10).
- Q11 ✅ **Out-of-scope policy:** Implementation Agent suggests a follow-up — comment ends with "*reply `/file-followup` and I'll create a new issue capturing this with context from the thread*".
- Q12 ✅ **Reporter iteration cap:** flat 5. Spec size doesn't predict iteration count; outliers route via escalation.

**v5** — Locked v4 open questions (Q13 24h auto-confirm, Q14 flat 3 human-loop cap, Q15 every-human-commit reporter ping).
**v4** — Flow re-ordered: humans review after reporter approves; unified PR on `agent/spec-<NNN>`.
**v3** — Added Implementation Agent + per-spec preview environments + reporter iteration loop.
**v2** — Added Spec Generator agent.
**v1** — Original four-pillar plan.

---

## ⚠️ v6 superseded changelog detail (v5 entry preserved for history)

**v5 — policy lock-ins from v4 open questions**
- Q13 ✅ **24h of silence after the last spec revision auto-confirms intent.** Confirmed as the default. Reporter can still `/confirm` to short-circuit. Documented in §5.3.1.
- Q14 ✅ **Human-refinement loop cap is a flat 3** for both design specs and fix-briefs. Documented in §5.4.3.
- Q15 ✅ **Every human commit on `agent/spec-*` triggers an automatic reporter ping** (changed from v4's "only if user-visible"). New workflow `notify-reporter-on-human-commit.yml`. New label `awaiting-reporter-reconfirm`. PR cannot move to `awaiting-devops` until the reporter re-confirms (`/approve`) or 24h pass silently. Details in §5.4.3 and §5.4.6.

**v4 — flow re-ordered**
- **The Implementation Agent now starts as soon as the reporter confirms intent**, not after humans merge the spec. The reporter sees a working preview faster; humans aren't a serial bottleneck twice.
- **Spec PR and implementation PR are unified.** Spec Generator and Implementation Agent commit to the *same branch* (`agent/spec-<NNN>`). The PR contains the spec file + the code; humans review the combined artifact once.
- **Three pipeline stages instead of two:** ① Capture intent → ② Build & validate with reporter → ③ Human review & ship.
- **Two separate human gates after reporter approval:** code-reviewer (quality + correctness + tenancy) then DevOps (rollout). Same human can play both, but the gates are distinct.
- **Human-refinement loop with cap 3.** Humans push commits or ask the agent to revise; if their changes touch user-visible behaviour, the reporter is re-pinged.
- New risk: human rubber-stamping after the reporter approves (mitigated by a CODEOWNERS checklist).

**v3** — Added Implementation Agent + per-spec preview environments + reporter iteration loop.
**v2** — Added Spec Generator agent.
**v1** — Original four-pillar plan.

---

## 1. Where we are today

Unchanged from v3. Anchoring assumptions: Odoo 19 multi-tenant via `dbfilter=^%d$`, 43 custom addons, cross-platform Railway + Fly staging deploy with parity gate, `saas_tenant_gate` + `saas_provisioning_gateway` + `saas_filestore_backup` control-plane addons, `docs/superpowers/{specs,plans}/` workflow in informal use.

---

## 2. Pillar A — Spec-Driven Development

Two spec shapes: **design spec** (heavyweight, for features) and **fix-brief** (lightweight, for bugs). Both live in `docs/superpowers/specs/`. Both enforced by the `spec-required` CI check.

### What changed in v4: the spec lifecycle

In v3 a spec PR was its own thing — humans reviewed and merged the spec, then implementation started on a separate branch. In v4, the spec file is the *first commit* of a longer-lived branch that ends up containing the implementation as well. Lifecycle of `agent/spec-<NNN>`:

```
commit 1   [spec-generator]    docs/superpowers/specs/<slug>-design.md (draft)
commit 2   [spec-generator]    spec updated per reporter Q&A — intent-confirmed
commit 3+  [impl-agent]        custom-addons/.../models, views, tests
commit ?   [impl-agent]        iteration N — preview-only changes from reporter feedback
commit ?   [human]             refactor / spec refinement / final polish
[merge to main by DevOps]      after both human gates pass
```

There is one PR open at any time per issue, and it accumulates the work. Reviewers always see "the whole package" — the spec, the diff, the conversation with the reporter, and the preview URL.

Template sections (unchanged from v3): goal · non-goals · tenancy impact · data model · API surface · security · test plan · rollout · observability · open questions.

---

## 3. Pillar B — Branching & Environments

### 3.1 Branch model

- `main` — only long-lived branch.
- Feature/fix/chore: `feat/<slug>`, `fix/<slug>`, `chore/<slug>` (used by humans for direct work).
- **Spec-driven branches: `agent/spec-<NNN>`** — shared by Spec Generator + Implementation Agent + reviewing humans for a single issue. (Changed from v3, where each agent had its own branch namespace.)
- Hotfix: `hotfix/<slug>`.

### 3.2 Environments

Unchanged from v3: dev · CI · staging × 2 · per-spec preview · agentlab · prod × 2.

### 3.3 Per-client rollout

Unchanged: `pool_id`, `wave`, `last_migrated_sha` on `saas.tenant`; `saas.tenant.migration.job` queue.

### 3.4 The `promote-to-prod` workflow

Unchanged: `canary` → 24h → `w1` → 48h → `w2`.

---

## 4. Pillar C — Three-Gate Test Ladder

Unchanged from v3 in structure. Preview envs run an abbreviated Gate 1 before the URL is ever posted to the reporter — they never see a broken preview.

---

## 5. Pillar D — Six AI Agents (5 engineering + 1 customer-facing)

### Agent roster at a glance (v6)

| Agent | Bucket | Trigger | Output | Autonomy |
|---|---|---|---|---|
| **Spec Generator** | engineering | New `feature-request` / `bug` issue, plus reporter replies until intent-confirmed | Spec on `agent/spec-<NNN>` + issue comments | Drafts only; cannot mark intent-confirmed without reporter signal |
| **Implementation Agent** | engineering | Spec marked `intent-confirmed` | Code commits on same branch + preview env + reporter iteration | Iterates with reporter; humans gate merge |
| **Code Agent** | engineering | Cron every 6h | Autonomous improvement PRs | Backlog-driven |
| **Security Agent** | engineering | Cron every 12h + critical CVE | Security PRs + issues | Some loops issue-only |
| **Optimization Agent** | engineering | Cron daily | Performance PRs | Backlog-driven |
| **Support Triage Agent** *(v6)* | customer-facing | End-user opens chat in Odoo app | Resolved chat OR filed `source:chatbot` GitHub issue OR escalation to support inbox | Auto-resolves with KB; files issues with confidence threshold; never auto-approves PRs |

### 5.1 Common agent shape — portable runtime *(v7)*

All six agents sit on a hexagonal runtime — agent core is pure Python depending only on **port interfaces**; **adapters** bind to specific vendors. One OCI image (`odoo-saas-agents:<version>`) runs every agent. Selection of bindings is a config file:

```
LLM provider     ↔  Claude (default via LiteLLM) · OpenAI · Gemini · Ollama · vLLM
Repo             ↔  GitHub (default) · GitLab · Gitea · LocalGit
Issue tracker    ↔  GitHub Issues (default) · GitLab Issues · Linear · Jira
Notifier         ↔  Slack (default) · Teams · Discord · Email · Webhook
Secret store     ↔  EnvVar (default) · GHA Secrets · Vault · K8s · Fly · Railway
Artifact store   ↔  S3-compatible (default) · GCS · LocalFS
Compute env      ↔  Fly (default) · Railway · Kubernetes · DockerLocal
Knowledge base   ↔  pgvector (default) · Chroma · Pinecone · Weaviate
Event bus        ↔  GitHub webhook (default) · Redis · NATS · LocalCron
Logger           ↔  StdJSON (default) · Loki · Better Stack · Datadog
```

**Day-one bindings are unchanged from v6** — Claude + GitHub + Slack + Fly + pgvector. The runtime is what makes "move off Anthropic" or "self-host the whole stack" a 1-week migration instead of a rewrite.

CI invocation looks the same across platforms:

```
GitHub Actions:    docker://ghcr.io/<org>/odoo-saas-agents:v1   args: run spec-generator …
GitLab CI:         docker run ghcr.io/<org>/odoo-saas-agents:v1 run spec-generator …
Kubernetes Job:    image: ghcr.io/<org>/odoo-saas-agents:v1     args: [run, spec-generator, …]
Local cron:        docker run --env-file ~/.agents.env ghcr.io/<org>/odoo-saas-agents:v1 run code
```

Full design: [`docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md`](superpowers/specs/2026-05-16-portable-agent-runtime-design.md).

Otherwise: CHARTER.md scopes each agent · `agent-guardrails` CI enforces hard rules · spend caps per agent and per loop · kill switch via `agents/kill-switch.yml` repo variable.

### 5.2 The agentlab environment (unchanged)

`odoo-saas-odoo-agentlab` Fly app, daily masked restore from staging.

### 5.3 The Spec Generator agent

**Trigger:** GitHub issue with label `feature-request` or `bug`. Also re-triggered by reporter comments on the issue until intent is confirmed.

**Output:** A spec file committed to `agent/spec-<NNN>` (PR opened on first commit, kept open). A summary comment on the original issue asking the reporter to confirm intent and answer open questions.

**Bug repro on agentlab:** three outcomes — `repro-confirmed`, `needs-repro-info`, `needs-fixture`. (Unchanged from v3.)

**Quality checks** (`.github/workflows/spec-quality.yml`): template completeness, tenancy-impact non-empty, ≥ 1 open question on design specs, regression-test sketch on fix-briefs, addon names mentioned.

#### 5.3.1 The intent-confirmed handoff *(v4)*

Spec Generator does NOT wait for a human merge. Instead:

1. Drafts spec → posts on issue: "I drafted a spec. Please confirm intent and answer these questions."
2. Reads reporter replies → updates the spec file → comments "Updated. Anything else?"
3. When the reporter signals intent-confirmed — by commenting `/confirm`, adding label `intent-confirmed`, or staying silent for 24h after the last revision — Spec Generator:
   - commits a final "[spec-generator] intent confirmed" marker on the branch,
   - adds label `intent-confirmed` to the PR,
   - fires the `implementation.yml` workflow.
4. Spec Generator stays available throughout the rest of the lifecycle to refine the spec on request (e.g. if the human reviewer asks for spec clarifications, or the Implementation Agent flags a contradiction).

### 5.4 The Implementation Agent

**Charter:** turn an intent-confirmed spec into a working preview the reporter can validate. Iterate with the reporter. Then hand the unified PR to humans for code review, refinement, and DevOps-led rollout.

**Allowed scope:** `custom-addons/**` (write), `docs/superpowers/plans/**` (write), tests everywhere. **NEW in v4:** can also push minor corrections to its own spec file under `docs/superpowers/specs/**` if it discovers contradictions during implementation — every such commit is prefixed `[impl-agent] spec correction:` so humans can spot them in review.

Cannot touch `infra/**`, workflows, Dockerfile, charters.

#### 5.4.1 Flow

```
Spec PR labelled intent-confirmed (Spec Generator just added it)
    │
    ▼
GHA workflow agents/implementation/.github/workflows/implementation.yml
    │
    1. Check out the same branch agent/spec-<NNN> Spec Generator opened
    2. Read the spec file at HEAD
    3. Write a plan under docs/superpowers/plans/YYYY-MM-DD-<slug>.md
    4. Implement the code per the plan (commits on same branch)
    5. Run abbreviated Gate-1 in agentlab (build · lint · security · tests)
         - if fails: try fix, max 3 retries
         - if 3 retries fail: escalate (label needs-human)
    6. Spawn odoo-saas-preview-spec-<NNN> on Fly (infra/fly/preview/spawn.sh)
    7. Seed with masked data (one tenant DB preview_<NNN>)
    8. Deploy the branch image to the preview env
    9. Comment on the original issue:
         "🚀 Preview ready: https://preview-<NNN>.<your-domain>
          Login: reviewer@preview.<domain> / <one-time-password>
          What I built: …
          Notes / unresolved: …
          Reply when tested. /approve to ship or comment with changes."
   10. PR label moves: intent-confirmed → awaiting-reviewer
   11. Notify Slack #devops-implementations (FYI)
```

#### 5.4.2 Reporter iteration loop

Workflow `implementation-iterate.yml` listens for `issue_comment.created` and `issues.labeled`:

```
On issue_comment.created OR issues.labeled:
    1. Is this an issue with a PR labelled awaiting-reviewer? If no, exit.
    2. Classify comment:
         "/approve" or label reviewer-approved   → APPROVAL path
         change-request text                    → ITERATION path
         "/escalate" or label needs-human       → ESCALATION path
         off-topic                              → ignore (log)

ITERATION path:
    3. Read comment + recent thread + current spec
    4. Out-of-scope check:
         - If requested change extends beyond the spec:
             - Comment: "That's out of scope. Open a new issue, or
                comment to update the spec first."
             - Do not implement.
    5. In-scope:
         - Push commits modifying the implementation
         - Re-run abbreviated Gate 1 (must stay green)
         - Redeploy to the same preview URL
         - Comment with what changed
    6. Increment iteration counter (label iter-N)
    7. If iter-N > 5 → ESCALATION

APPROVAL path:
    8. Label: awaiting-reviewer → reporter-approved → awaiting-human-review
    9. Slack #devops-implementations + ping CODEOWNERS of touched addons:
         "Reporter approved PR #<N>. Please review the spec, the diff,
          and the conversation thread. Preview still live at <URL>."

ESCALATION path:
   10. Label needs-human; preview stays up; iteration paused.
```

#### 5.4.3 Human review (NEW gate in v4)

When the PR enters `awaiting-human-review`, a CODEOWNERS reviewer:

- **Reviews the spec** — is what was built consistent with what the reporter asked for? Are non-goals respected? Tenancy impact correctly characterised?
- **Reviews the reporter conversation** — anything the reporter accepted that they shouldn't have (security-sensitive, performance time-bomb, tenant-boundary risk)?
- **Reviews the diff** — code quality, idiomatic Odoo, test coverage, security, performance.
- **Refines as needed** — three ways:
  1. **Push commits directly** to `agent/spec-<NNN>` (humans are not blocked by agent guardrails).
  2. **Ask the Implementation Agent to revise** by adding label `human-requests-changes` with a comment describing what should change. Agent then iterates and re-deploys preview.
  3. **Ask the Spec Generator to refine the spec** by adding label `spec-refinement-needed`. Spec Generator updates the spec; if it materially changes scope, the Implementation Agent re-evaluates (may trigger another reporter check-in).
- **Approves and labels** `human-review-approved` when satisfied.

Cap on the human-refinement loop: **3 iterations** — flat across design specs and fix-briefs (v5 Q14). If the reviewer is still making substantive changes after the third round, the work is paused for a synchronous review with the reporter — something's gone wrong upstream.

CODEOWNERS approval is non-bypassable: the PR cannot move to `awaiting-devops` without `human-review-approved`.

#### 5.4.3.1 Automatic reporter ping on human commits *(v5 Q15)*

Every commit pushed to an `agent/spec-*` branch by a non-agent author triggers two things automatically:

1. **Preview redeploy** — the preview env `odoo-saas-preview-spec-<NNN>` rebuilds and redeploys at the same URL, so the reporter is always looking at the latest state.
2. **A ping comment on the original issue**, posted by the bot, with:
   - Commit SHA, author, message.
   - A one-line summary of the diff (file count, key paths touched).
   - A note flagging whether the commit appears **user-visible** (touches `views/`, `static/`, `controllers/`, qweb templates, model labels) or **internal-only** (tests, comments, refactors).
   - The (same) preview URL.

The PR label moves: `human-review-approved` → **`awaiting-reporter-reconfirm`**. The PR cannot move on to `awaiting-devops` until either:

- the reporter comments `/approve` (or adds label `reporter-approved` again), **or**
- 24 h elapse from the most recent human commit with no objection from the reporter.

This replaces v4's checkbox-mandatory step. Humans no longer have to remember to tick a box — the system always tells the reporter.

**Debouncing.** Multiple human commits within a 1-hour window batch into a single ping comment (the comment edits itself with each new commit during the window). The 24h auto-reconfirm timer resets on each new commit.

**Implementation.** New workflow `agents/implementation/.github/workflows/notify-reporter-on-human-commit.yml`:

```yaml
on:
  push:
    branches: ['agent/spec-*']
jobs:
  notify:
    if: github.event.head_commit.author.email !=
        'spec-generator-bot@<your-domain>' &&
        github.event.head_commit.author.email !=
        'implementation-bot@<your-domain>'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: redeploy preview
        run: ./infra/fly/preview/redeploy.sh "${{ github.ref_name }}"
      - name: ping reporter
        run: ./agents/implementation/scripts/ping-reporter.sh
              --branch "${{ github.ref_name }}"
              --sha "${{ github.sha }}"
              --author "${{ github.event.head_commit.author.name }}"
              --message "${{ github.event.head_commit.message }}"
              --debounce-window 1h
      - name: relabel PR
        run: gh pr edit --add-label awaiting-reporter-reconfirm
                       --remove-label human-review-approved
```

**Branch protection.** `agent/spec-*` branches refuse force-push and history rewrite, so the workflow can't be circumvented by a rebase.

**Bot identity.** The agents' commits are authored as `spec-generator-bot@<your-domain>` and `implementation-bot@<your-domain>` so the workflow can distinguish them from human commits and skip the ping on agent self-iteration (the agent already pings on its own iterations).

#### 5.4.4 DevOps handoff

When `human-review-approved`, DevOps (`prod-deployers` team) takes over:

- Final sanity check — read the addon-upgrade-matrix output, the migration-dry-run report, the preview env smoke logs.
- Merge the PR to `main`. Preview env scheduled for destruction by `preview-cleanup.yml`.
- Gate 2 runs automatically (cross-platform staging deploy + parity).
- After 24h staging soak, DevOps triggers `promote-to-prod wave=canary` → 24h → `w1` → 48h → `w2`.

DevOps's job is *deployment safety*, not code review — that already happened at the previous gate. If DevOps spots a code issue, they push it back to `awaiting-human-review` rather than fixing it themselves.

#### 5.4.5 Preview environment infrastructure (unchanged from v3)

`infra/fly/preview/spawn.sh` · `shared-cpu-1x` machines · 5 GB Postgres · masked agentlab snapshot · wildcard cert · one-time reviewer login · nightly `preview-cleanup.yml`. Max 10 concurrent.

#### 5.4.6 PR lifecycle (v4 label state machine)

```
spec-drafted              ← Spec Generator opened the PR (spec file only)
awaiting-reporter-confirm ← Spec Generator commented with questions
intent-confirmed          ← Reporter signalled OK (or 24h silence)
implementing              ← Implementation Agent writing code
awaiting-preview          ← Preview env spinning up
awaiting-reviewer         ← URL posted to issue, waiting for reporter
iterating                 ← Implementation Agent applying a change
reporter-approved         ← Reporter /approved
awaiting-human-review     ← CODEOWNERS reviewing the package
human-refining            ← Reviewer pushing commits or directing agent
human-review-approved     ← CODEOWNERS signed off
awaiting-reporter-reconfirm ← (v5) every human commit pings reporter; gate
                              clears via /approve OR 24h silence
awaiting-devops           ← Ready for merge to main
merged                    ← In main; preview destroyed
rolling-out               ← In wave promotion (canary → w1 → w2)
done                      ← Wave-2 complete
needs-human               ← Escalated; loop paused
abandoned                 ← Reporter silent 14d OR PR closed without merge
```

#### 5.4.7 Quality gates during iteration (unchanged)

Every iteration must pass abbreviated Gate 1 before the preview URL is shown. HIGH-severity security findings block the preview from being posted. Three consecutive Gate-1 failures → escalate.

#### 5.4.8 What the agent must NOT do (unchanged + tightened)

- Implement anything not in the spec → polite refusal.
- Skip tests → never.
- Commit secrets, credentials, real customer data → never.
- Rewrite the spec wholesale to match a flawed implementation → only minor corrections allowed, clearly prefixed; substantive spec changes must come from Spec Generator or a human via `spec-refinement-needed`.

#### 5.4.9 Handling silence and abandonment

7d silence → ping. 14d silence → label `abandoned`, destroy preview, weekly digest to DevOps.

#### 5.4.10 Cost & cadence

Event-driven. 5 open PRs max. 5 reporter iterations + 3 human iterations cap. Spend cap USD 100/week. Preview cap 10 concurrent.

#### 5.4.11 Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Agent can't implement spec | Gate 1 fails 3× | Escalate; humans rewrite spec or implement |
| Out-of-scope creep | Classifier matches `out-of-scope` heuristic | Polite refusal + pointer to spec |
| Spec wrong | Agent self-detects mid-plan | Files issue to Spec Generator; pauses; humans rebalance |
| Preview won't deploy | Fly provisioning fails | Retry 3×; escalate; PR labelled `infra-issue` |
| Reporter loop > 5 | Iteration counter | Escalate to humans |
| Human loop > 3 | Iteration counter | Sync review with reporter — something's off |
| Reporter silent | 7d / 14d timers | Ping; abandon |
| Reviewer rubber-stamps | (humans) | CODEOWNERS checklist; Security/Code agents post pre-review report |

### 5.5–5.9 Code, Security, Optimization, notifications, cost (unchanged from v3)

### 5.10 Support Triage Agent *(new in v6, customer-facing bucket)*

**Charter:** customer-facing intake. Lives inside the Odoo app as a chat widget. Answers user questions, helps decide bug vs feature vs config vs user-error, offers workarounds, and files GitHub issues that feed the existing v5 pipeline.

**Full design:** [`docs/superpowers/specs/2026-05-16-support-triage-agent-design.md`](superpowers/specs/2026-05-16-support-triage-agent-design.md). Summary below.

**Components:**
- New addon `saas_support_chatbot` (alongside existing `saas_*` addons), installed per-tenant, gated by `saas_tenant_gate.support_chatbot_enabled` flag.
- New Fly app `odoo-saas-support-gateway` holding the Claude API token, GitHub PAT, vector store (pgvector with addon docs + Obsidian + past specs), and the audit log.

**Three intake outcomes:**
1. **Bot resolves** — KB has the answer; no GitHub issue. Counts toward deflection rate (target ≥ 40 %).
2. **Files GitHub issue** — labels `bug` or `feature-request` plus `source:chatbot`; body sanitised by 3-layer PII mask (deny-list → tenant allow-list → LLM cleanup pass); transcript attached.
3. **Escalates to support inbox** — sensitive topics (billing, account recovery, security, legal) never reach GitHub.

**Bidirectional sync:** gateway subscribes to GitHub webhooks; when the v5 pipeline progresses (Spec Generator commented, Implementation Agent posted preview URL, PR merged, wave-2 deployed), the bot posts an update back to the originating chat thread in the user's language.

**Phasing (Phase 9–10 of the master roadmap, §11):**
- Phase 9a (weeks 18–20) MVP: widget + chat + file issues.
- Phase 9b (weeks 21–22): back-sync from GitHub webhooks.
- Phase 9c (weeks 23–24): in-chat `/approve` and `/iterate` map to GitHub.
- Phase 9d (weeks 25–26): per-tenant context (recent errors, current view).

**Guardrails:**
- Confidence threshold ≥ 0.5 before filing; below that, asks clarifying questions instead.
- 30 messages / user / hour; 5 issues / tenant / day; 1 sensitive escalation / user / hour.
- Per-tenant feature flag — can be flipped off instantly.
- Service-account GitHub PAT scoped only to `issues:write` + `issue_comments:write`.
- Sensitive-topic detector at `infra/agentlab/sensitive-topics.yml` owned by `security-leads` (same group as the masking allow-list).
- Spend cap < USD 300 / month across all tenants.

---

## 6. End-to-end flow (v4 happy path)

```
[t=0]         Customer emails support@... about a missing report.
[t+5m]        Support inbox auto-creates GitHub issue #1500 with
              label `feature-request`.
[t+6m]        Spec Generator opens PR #1501 on branch agent/spec-1500
              with a draft spec; comments on #1500 asking 3 questions.
[t+1h]        Reporter answers in #1500.
[t+1h 10m]    Spec Generator updates spec file; comments "OK?"
[t+2h]        Reporter comments `/confirm`. Label intent-confirmed
              fires the Implementation Agent.
[t+2h 5m]     Impl Agent picks up the branch; writes plan; codes.
[t+2h 30m]    Preview env odoo-saas-preview-spec-1500 deployed; URL +
              one-time creds posted to #1500. Label awaiting-reviewer.
[t+5h]        Reporter logs in, finds an issue with the XLSX output.
[t+5h 20m]    Impl Agent iterates; redeploys preview. Iter 2 of 5.
[t+6h]        Reporter comments `/approve`. Label awaiting-human-review.
              CODEOWNERS pinged in Slack.
[t+1d]        Lead-dev reviews. Pushes one stylistic refactor commit.
              Asks Impl Agent to add a missing edge-case test via label
              `human-requests-changes`. Iter 1 of 3.
[t+1d 1h]     Impl Agent adds test; Gate 1 still green; preview still up.
[t+1d 2h]     Lead-dev approves: label human-review-approved.
              PR labelled awaiting-devops.
[t+1d 3h]     DevOps does final sanity check, merges PR #1501 to main.
              Preview env queued for destruction.
[t+1d 3h 30m] Gate 2 green; both staging deploys + parity green.
[t+2d 3h 30m] 24h staging soak complete. DevOps triggers
              promote-to-prod wave=canary.
[t+3d 3h 30m] 24h canary soak. promote-to-prod wave=w1.
[t+5d 3h 30m] 48h w1 soak. promote-to-prod wave=w2.
[t+5d 4h]     Spec Generator weekly back-translation drafts "what we
              shipped" reply for the support inbox.
```

Total elapsed: ~5 days customer email → all-tenants prod. Reporter sees a real preview ~2.5 hours after they confirmed intent. Total *active* engineering time is ~3–4 hours.

**v3 vs v4 timing.** In v3, the reporter waited for humans to merge the spec PR (~1 day) before the agent started building. In v4, the agent starts as soon as the reporter says `/confirm`. That saves the worst-case 24+ hours from the reporter's perspective. The trade-off is that humans review the combined package once at the end, which is a heavier single review — but it's also a more informed one.

---

## 7. Promotion, rollback, hotfix (unchanged from v3)

§7.1 `promote-to-prod.yml` · §7.2 per-tenant pause · §7.3 `rollback-prod.yml` · §7.4 hotfix flow.

---

## 8. Per-tenant migration safety (unchanged from v2)

Size buckets · per-job timeout · lock-aware migrations · maintenance windows · backup pin.

---

## 9. Observability & audit (unchanged from v3)

Tagged logs · per-tenant Grafana · alerts · `saas.audit.event` append-only with S3 Object Lock. Preview env events written to audit log.

---

## 10. Agent governance — and the rubber-stamp risk

(v2 §9 + a new piece specific to v4.)

The v4 flow puts a heavier weight on the human review at the end, because two things converge there: code review *and* the implicit "is what the reporter approved actually safe to ship". To stop reviewers from rubber-stamping reporter approval:

- **Pre-review report.** Before the PR enters `awaiting-human-review`, the Security Agent and Code Agent each post one automated comment on the PR with findings: `bandit` results, record-rule audit on touched models, coverage delta, duplicate-code matches, performance heuristics. Reviewer must acknowledge these by reacting or commenting; the PR cannot be approved until both reports show a reactji.
- **CODEOWNERS checklist** in the PR template — five must-tick items:
  1. Spec's tenancy-impact section is accurate for what was actually built.
  2. Tests cover the new behaviour AND a negative case.
  3. No regression in `addon-upgrade-matrix`.
  4. *(v5)* All human commits on this branch have a reporter ping comment on the issue, and the reporter either `/approved` after the last one or 24h silence elapsed.
  5. Security agent's pre-review report is clean OR findings are noted/dismissed with reason.
- **Sampling.** 1 in 10 merged PRs are audited by a second reviewer in the following week (not blocking, but trends are tracked).
- **Quarterly review** (unchanged) covers reviewer hit rate alongside agent hit rate.

Other governance pieces (charters spec-tracked, quarterly review, agent-on-agent review, read-only weeks) carry over unchanged.

---

## 11. Roadmap (10 phases — v7 adds the portable agent runtime as Phase 6)

1. **Week 1** — Spec workflow enforcement.
2. **Weeks 2–3** — Test ladder hardening.
3. **Weeks 4–5** — Production environments + promote/rollback.
4. **Week 6** — Per-client rollout polish (migration queue, flags, size buckets).
5. **Weeks 7–8** — Observability + agentlab.
6. **Weeks 9–10 *(v7)*** — **Portable agent runtime + adapter library.** Skeleton `agents/` package; ports + default adapters (Claude via LiteLLM, GitHub, Slack, Fly, pgvector, EnvVar, GHWebhook, StdJSON); contract test suite per port; `agents config validate` CI; one trivial smoke agent running end-to-end. Without this, every later agent would be coupled to today's vendors.
7. **Weeks 11–12** — Spec Generator agent + `intent-confirmed` event + label state machine *(built on the runtime)*.
8. **Weeks 13–15** — Implementation Agent + preview infra + reporter iteration loop + human-review labels + CODEOWNERS checklist.
9. **Weeks 16–19** — Code · Security · Optimization improvement agents. Security + Code online by end of week 18.
10. **Weeks 20–28** — Support Triage Agent. Sub-phases:
    - 10a (20–22) MVP — addon + gateway + KB ingest + file issues.
    - 10b (23–24) — back-sync from GitHub webhooks; bilingual ES/EN.
    - 10c (25–26) — in-chat `/approve` and `/iterate`.
    - 10d (27–28) — per-tenant context awareness.

**Optional Phase 11 — alternative-stack validation.** Pick one alternative stack (e.g. GitLab + GPT-4o + Teams) and stand up a twin of the staging pipeline. Run weekly smoke. Proves portability is real, not aspirational.

Cross-cutting: every phase follows the spec workflow; each ends with a retro ADR.

---

## 12. Success metrics (v4)

| Metric | Target | Notes |
|---|---|---|
| % of merged PRs with linked spec | ≥ 90% | weekly |
| Median time issue → spec PR drafted | < 10 min | weekly |
| Median time spec drafted → **intent-confirmed** | < 4 h | v4: replaces "→ merged" |
| Median time intent-confirmed → preview URL posted | < 30 min | v4: new |
| Median time preview posted → reporter `/approve` | < 2 d | continuing from v3 |
| Median iteration count (reporter loop) | ≤ 2 | v3 |
| Median time `/approve` → human-review-approved | < 1 d | v4: new gate |
| Median iteration count (human refinement loop) | ≤ 1 | v4: new |
| Reporter satisfaction (post-merge survey, 1–5) | ≥ 4.0 mean | v3 |
| % human reviews that re-engaged reporter | tracked, no target | sanity |
| Median time main → staging | < 30 min | unchanged |
| Median time staging → prod canary | 24–48 h | unchanged |
| Migration job success rate / tenant / wave | ≥ 99% | unchanged |
| Cross-platform parity gate hit rate | 100% | unchanged |
| Agent PR merge rate | ≥ 50% by week 20 | unchanged |
| Implementation Agent escalation rate | < 15% | unchanged |
| MTTD prod regression | < 5 min | unchanged |
| MTTR prod regression | < 30 min | unchanged |
| Mean weekly agent spend | < USD 250 | unchanged |
| Concurrent preview envs | ≤ 10 | unchanged |
| **% reviewer rubber-stamp suspicions on sample audit** | < 5% | v4: new, sampled |

---

## 13. Risks & mitigations (v4 additions in bold)

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Human rubber-stamping** *(v4)* | Reviewer waves through what the reporter approved without examining diff | Pre-review reports from Security + Code agents; CODEOWNERS checklist; 10% sampling audit |
| **Wasted agent work on a flawed spec** *(v4)* | Spec turns out to be wrong direction *after* implementation; agent time burned | 24h "confirmation pause" allows reporter to step back; intent-confirmed requires explicit signal or 24h silence (not just initial draft); agent escalates if it detects internal spec contradictions |
| **Human refinement happens behind reporter's back** *(v5: tightened)* | Reviewer changes anything — UX, internals, refactors — without reporter visibility | **Every** human commit on `agent/spec-*` auto-pings reporter + redeploys preview; PR cannot merge until `/approve` or 24h silence after the last human commit |
| Implementation loop never converges | Reporter keeps requesting changes; spend balloons | 5-iter cap on reporter loop; 3-iter cap on human loop; per-PR spend cap |
| Reporter approves something broken | Bug ships even after the loop | Human review is a hard gate AFTER reporter approval (v4 makes this explicit) |
| Preview env leaks data | PII exposed via reviewer login | Agentlab masking; one-time creds; private issues |
| Preview cost spiral | 100 simultaneous specs | 10 concurrent cap; auto-stop; nightly destroy |
| Out-of-scope creep | Reporter or human asks beyond spec | Agent refuses; new spec PR required |
| Spec misreads intent | Wrong work built | Reporter CC'd; intent-confirmed requires reporter signal; ≥ 1 open question on design specs |
| Per-tenant migration drift | One tenant fails, blocks wave | Per-tenant queue; failures isolated |
| Tenancy boundary regression | Data leaks across tenants | Tenancy loop is issue-only; CODEOWNERS on `saas_tenant_gate/security/**` |
| Large-tenant timeouts | 50 GB tenant migration runs for hours | Size buckets; per-job timeout; lock-aware migrations |
| PII leak into agentlab/preview | Masking misses a column | Allow-list; weekly random-row audit |
| Hotfix bypass erosion | Hotfix path becomes default | Retro fix-brief in 48h or revert |

---

## 14. What "done" looks like (v4)

- **The reporter sees a real Odoo URL within ~30 min of confirming intent**, validates the actual change, and signs off — *before* humans are asked to review.
- **Humans review the package** — spec, diff, reporter conversation, agent pre-review reports — once at the end, with all context in front of them.
- A single PR per issue accumulates every artifact: spec, plan, code, conversation, preview link.
- ≥ 90% of merged PRs link to a spec or fix-brief.
- 8 green checks gate `main`; 4 more checks + 24h soak gate prod.
- A single client can roll forward or be paused independently via the wave system.
- Five AI agents with distinct charters; humans always merge.
- Either Railway or Fly can fail without taking customers down.
- An auditor can answer "who deployed what to whom when, and why" from `saas.audit.event`.

---

## 14a. Vendor-lock-in audit *(v7)*

| Vendor in default stack | Lock-in risk | Migration cost (with v7 runtime) |
|---|---|---|
| **Anthropic Claude** | Pricing, model deprecation, regional outage | **Hours.** LiteLLM fallback chain already configured; flip default to `gpt-4o` in `agents/config.yml`. |
| **GitHub (repo + Actions + Issues)** | Pricing, outage, want to self-host | **~1 week.** Implement `repo_gitlab.py` and `issues_gitlab.py` (some scaffolding shipped); migrate webhooks; replace `.github/workflows/` with `.gitlab-ci.yml` invoking the same OCI image. |
| **Slack** | Pricing, vendor lock for company comms | **1 hour.** Switch `bindings.notifier` to `discord` / `teams` / `email` / `webhook`. |
| **Fly.io** | Pricing, capacity | **2–3 days for agentlab / preview envs.** Cross-platform parity for Odoo prod is already a v6 property. Implement `compute_railway` or `compute_kubernetes` if not done. |
| **Better Stack (logs)** | Vendor swap | **1–2 days.** Implement `logger_loki` or `logger_datadog`; flip binding. |
| **Cloudflare R2 / S3** | Pricing | **Free.** S3 adapter is endpoint-agnostic; works with MinIO, Backblaze, AWS, GCS-via-interop. |
| **LiteLLM (the LLM proxy itself)** | Project sunset, breaking change | **2–3 days.** Direct adapters for Claude/OpenAI/Gemini are shipped as fallback. |

No single vendor's failure can pin us; the worst case is GitHub (1 week of work).

---

## 15. Open questions

**Resolved in v6 (Q1–Q12) — see Changelog above.**
**Resolved in v5 (Q13–Q15).**

**Still open:**

- Vector store at scale: pgvector vs Pinecone/Weaviate — revisit if KB grows past ~100k chunks.
- Whether the chatbot should file a separate issue when a single conversation reveals multiple unrelated bugs/features.
- Whether to power a public docs site from the same KB — separate ADR if pursued.
- **(v7)** Should we run Phase 11 (alternative-stack validation) as a standing weekly job, or only on-demand before a vendor migration?
- **(v7)** Should improvement agents (code/security/optimization) be allowed to fall back to a local model (Ollama) under spend pressure, or always use the configured frontier model? Trade-off: cost vs review quality.
