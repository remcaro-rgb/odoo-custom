# Support Triage Agent — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** new addon `saas_support_chatbot` + new Fly app `odoo-saas-support-gateway` + new intake path in the v5 pipeline.

---

## 1. Goal

Add a customer-facing chatbot inside the Odoo SaaS app that:

1. Answers end-user questions about the app using a curated knowledge base.
2. Helps the user (collaboratively, via clarifying questions) decide whether their report is a bug, feature request, configuration issue, or user error.
3. Provides a workaround if one exists (from the KB or LLM-reasoned).
4. Files a GitHub issue with the right label and PII-masked context when appropriate, so the existing v5 intake pipeline (Spec Generator → Implementation Agent → reporter loop) takes over.
5. Keeps the customer updated in-chat as their report moves through the dev pipeline.

The chatbot becomes a **third intake source** alongside dev-filed GitHub issues and the email-to-issue support inbox.

---

## 2. Non-goals

- Replacing human support entirely. Sensitive issues (billing, account recovery, data deletion, security) still route to humans.
- Acting as a general-purpose Odoo chatbot. Scope is bounded to this SaaS deployment and its installed addons.
- Resolving bugs in-line. The bot offers workarounds; actual code fixes still go through the v5 dev pipeline.
- Cross-tenant context. Each tenant is isolated; the bot never references one tenant's data while serving another.
- Live human handoff during chat. Out-of-scope items escalate to the support inbox asynchronously.
- Anonymous chat. Logged-in Odoo users only — no public widget.

---

## 3. Architecture

### 3.1 Components

```
┌─────────────────────────────────────────────────────┐
│ Odoo tenant (any prod tenant with the flag enabled) │
│                                                     │
│  ┌──────────────────┐    ┌──────────────────────┐  │
│  │ Chat widget (JS) │←──►│ saas_support_chatbot │  │
│  │ web/static/      │    │   addon              │  │
│  │ + qweb templates │    │                      │  │
│  └──────────────────┘    └──────────┬───────────┘  │
│                                     │              │
│                                     ▼              │
│                       ┌──────────────────────────┐ │
│                       │ /support/chat controller │ │
│                       └────────────┬─────────────┘ │
│                                    │ HMAC-signed   │
└────────────────────────────────────┼───────────────┘
                                     │ HTTPS
                                     ▼
        ┌─────────────────────────────────────────────────┐
        │ Support Gateway (Fly app)                       │
        │ odoo-saas-support-gateway                       │
        │                                                 │
        │  ┌────────────────┐  ┌────────────────────┐    │
        │  │ Triage engine  │  │ RAG / KB           │    │
        │  │ (Claude SDK)   │←─│ pgvector           │    │
        │  └───────┬────────┘  └────────────────────┘    │
        │         │                                       │
        │         │  ┌────────────────┐                  │
        │         └─►│ GitHub API     │                  │
        │            │ (issues:write) │                  │
        │            └────────────────┘                  │
        │                                                 │
        │  ┌────────────────┐                            │
        │  │ Gateway events │  Postgres (separate DB)    │
        │  │ + audit        │  with pgvector             │
        │  └────────────────┘                            │
        └────────────┬────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────────────────────┐
        │ GitHub issue with label source:chatbot         │
        │ → enters Spec Generator (v5 pipeline)          │
        └────────────────────────────────────────────────┘
```

### 3.2 Why a separate gateway app

A new Fly app `odoo-saas-support-gateway` holds the Claude API token, the GitHub PAT, and the vector store. The Odoo addon talks to it over HTTPS with an HMAC-signed token.

Reasons:

- **Secret hygiene** — Claude/GitHub credentials live in one place, not in every tenant DB.
- **Shared KB** — the knowledge base (addon docs, FAQs, past specs) is non-tenant-specific. Storing it once on the gateway avoids 50× duplication.
- **Centralised rate-limit + audit** — easier to enforce per-tenant caps and write to a single audit stream.
- **Cost control** — one place to throttle, one budget to monitor.
- **Upgrade decoupling** — the gateway can update independently of tenant deployments (a model swap doesn't require a tenant migration).

### 3.3 Deployment topology

Same cross-platform pattern as the rest of the SaaS:

- Primary: Fly app `odoo-saas-support-gateway` (`shared-cpu-2x`, 2 GB RAM, primary region `iad`).
- Backup: Railway service `support-gateway` (cold standby; promoted manually if Fly fails).
- DB: dedicated Fly Postgres `odoo-saas-support-gateway-db` with pgvector. Daily `pgbackrest` snapshots (reusing the existing pipeline).
- Per-region replication for read-heavy KB lookups (deferred to Phase D).

---

## 4. Tenancy impact

Per-tenant boundary is the most important property. Mechanisms:

- **Conversation data lives in the tenant DB.** Threads, messages, triage results are tables in each tenant DB; record rules scope them to `user_id == env.user` or to the local `Support Manager` group. No cross-tenant visibility, period.
- **Gateway requests carry a hashed tenant identifier.** When the Odoo addon calls `/v1/triage`, it sends `tenant_hash = sha256(<dbname>)[:12]`. The gateway never sees plaintext tenant names.
- **HMAC per tenant.** Each tenant installs the addon with a tenant-scoped HMAC secret issued by `saas_tenant_gate` and rotated quarterly via the existing `rotate-telemetry` pattern.
- **Knowledge base is shared.** It contains addon documentation, runbooks, FAQ — all non-customer data. No tenant data is ever embedded in the vector store.
- **GitHub issue identity is sanitised.** The reporter is recorded as `reporter:user_<sha256-prefix>@tenant:<sha256-prefix>`. The mapping `hash → real identity` is stored only on the gateway and only accessible to operators with `support-leads` membership.
- **New per-tenant feature flag** in `saas_tenant_gate`: `support_chatbot_enabled` (default `false`; opt-in per tenant via the control plane). Aligns with the wave-based rollout in the main plan.

---

## 5. Conversation flow

### 5.1 Resolved-in-chat (no issue filed)

```
User: "How do I export the aged-receivable report to Excel?"
Bot: [looks up KB; finds club_pos addon + custom report]
     "Here's how:
       1. Open Accounting → Reporting → Aged Receivable
       2. Click the gear icon → Export → XLSX
       3. The file downloads to your browser's default location.
      [link to docs] Did this help?"  [👍 / 👎]
User: 👍
Bot: [thread.state = 'resolved', resolution_kind = 'bot-resolved']
     "Glad I could help. Anything else?"
```

Counts toward the **deflection rate** (bot-resolved ÷ total). No GitHub issue. No engineering cost.

### 5.2 Triage → bug

```
User: "The aged-receivable report is showing duplicated rows."
Bot: [KB has no known workaround. Confidence as bug: 0.42 — not enough.]
     "I'd like to understand a bit more so I can route this correctly:
       - Does it happen every time, or only sometimes?
       - Did it start recently?
       - Which customer or filter were you using?"
User: "Every time, started after last week's update, customer ACME."
Bot: [confidence as bug now 0.86. Searches existing issues for duplicates.
     Finds nothing similar. LLM generates a candidate workaround.]
     "Thanks. This looks like a real bug — I don't see it reported before.
     As a workaround until the team fixes it: switch to the v2 view
     (Settings → Reports → Aged Receivable v2). It uses a different
     query and shouldn't show the duplication.

     I've filed your report as issue #1500 on our tracker. I sanitised
     the customer name and your tenant details before filing. I'll
     let you know here as soon as there's progress."
[Bot calls gateway /v1/file-issue → GitHub /issues with label
 `bug`, `source:chatbot`, body per §7.4, masked transcript attached.]
```

### 5.3 Triage → feature request

```
User: "Can we get a dark mode?"
Bot: [KB confirms no dark mode shipped. Classifier: 'feature' confidence 0.94]
     "Dark mode isn't in the product today. Want me to file it as a
     feature request? The team triages these weekly."
User: "Yes."
Bot: [files with label `feature-request`, `source:chatbot`. Captures
     the user's brief use case from the chat.]
     "Filed as #1501. I'll ping you here if it's picked up."
```

### 5.4 Triage → configuration or user error

```
User: "I can't find the inventory module."
Bot: [gateway checks tenant's installed_addons via saas_tenant_gate.
     Inventory not installed.]
     "Inventory is an optional module that needs to be enabled. Two paths:
       a) If you're an admin in this tenant: Settings → Apps → install
          Inventory (free).
       b) If your SaaS plan doesn't include it: reply 'request inventory'
          and I'll route that to support."
User: "Request inventory."
Bot: [thread.state = 'escalated'; routes to the support inbox via email.
     NOT a GitHub issue — this is a sales/config request handled by humans.]
     "Got it. I emailed support; they'll follow up within one business day."
```

### 5.5 Sensitive topic → escalation

```
User: "My invoice payment was charged twice, please refund."
Bot: [sensitive-topic detector matches 'billing']
     "I can't process refunds myself, but I'm routing this to our
     support team now. They'll reply within one business hour."
[thread.state = 'escalated'. Email to support inbox with the user's
 message and tenant context. NO GitHub issue.]
```

### 5.6 Bidirectional sync — bot tells user about progress

The gateway subscribes to GitHub webhook events on issues it filed. When a relevant event arrives, it posts back to the originating chat thread.

```
[T+3 days: Implementation Agent posts preview URL on #1500]
Bot (same chat thread, in user's language):
   "Update on the duplicated-rows bug:
     ✅ The team built a fix. Try it here: [preview URL]
        Login: <one-time creds>
     Let me know in this chat if it solves it for you, or click here
     to /approve directly."  [Approve] [Iterate]
User: "Looks good." (or clicks Approve)
Bot: [maps to GitHub /approve on the linked PR via gateway.
     Comments on issue #1500 as the chatbot service account,
     forwarding the user's confirmation.]
   "Great — I told the team. They'll roll it out in waves over the
   next few days. I'll ping you here when it's live."
[T+8 days: wave-2 deploy complete]
Bot: "Your fix is live as of today. Thanks for reporting!"
```

---

## 6. Data model

### 6.1 In each tenant DB (the new addon's tables)

```python
class SaasSupportThread(models.Model):
    _name = 'saas.support.thread'
    _description = 'Support chatbot conversation thread'

    user_id           = fields.Many2one('res.users', required=True, index=True)
    state             = fields.Selection([
                          ('open','Open'),
                          ('resolved','Resolved by bot'),
                          ('escalated','Escalated to support inbox'),
                          ('filed','Filed as GitHub issue')],
                          default='open', index=True)
    triage_result     = fields.Selection([
                          ('bug','Bug'),
                          ('feature','Feature request'),
                          ('config','Configuration'),
                          ('user-error','User error'),
                          ('sensitive','Sensitive — human only'),
                          ('out-of-scope','Out of scope')])
    triage_confidence = fields.Float(help="0–1; bot's confidence in triage")
    resolution_kind   = fields.Selection([
                          ('bot-resolved','Bot resolved'),
                          ('workaround-given','Workaround given'),
                          ('issue-filed','Issue filed'),
                          ('escalated','Escalated')])
    github_issue_url  = fields.Char()
    github_pr_url     = fields.Char()
    language          = fields.Char(default='es_CO')
    last_activity_at  = fields.Datetime()

class SaasSupportMessage(models.Model):
    _name = 'saas.support.message'
    _order = 'create_date asc'

    thread_id     = fields.Many2one('saas.support.thread', required=True, ondelete='cascade')
    author        = fields.Selection([('user','User'),('bot','Bot'),('system','System')], required=True)
    body          = fields.Text(required=True)
    snippets_used = fields.Text(help="JSON: which KB snippets fed this response")
    pii_masked    = fields.Boolean(default=False, help="True for the masked-for-GitHub copy")
    feedback      = fields.Selection([('up','👍'),('down','👎')])
```

### 6.2 On the gateway (separate Postgres with pgvector)

```sql
-- knowledge base chunks
CREATE TABLE kb_chunks (
    id           uuid primary key,
    addon        text,
    title        text,
    body         text,
    embedding    vector(1024),
    source_url   text,
    version      text,
    updated_at   timestamptz default now()
);
CREATE INDEX kb_chunks_embed_idx ON kb_chunks USING ivfflat (embedding vector_cosine_ops);

-- per-tenant audit / events
CREATE TABLE gateway_events (
    id          bigserial primary key,
    tenant_hash text not null,
    user_hash   text,
    thread_hash text,
    event       text not null,   -- chat_message | file_issue | escalate | webhook_inbound
    payload     jsonb not null,
    cost_usd    numeric(8,4),
    created_at  timestamptz default now()
);
CREATE INDEX gateway_events_tenant_idx ON gateway_events (tenant_hash, created_at);

-- reporter mapping (only on gateway, never replicated out)
CREATE TABLE reporter_identity (
    hash         text primary key,
    real_user_id integer not null,
    real_dbname  text not null,
    created_at   timestamptz default now()
);
```

---

## 7. API surface

### 7.1 Odoo controller (in `saas_support_chatbot`)

```
POST /support/chat
  auth: standard Odoo session
  body: { thread_id?: int, message: string, language?: string }
  resp: { thread_id, bot_message, buttons?: [{label, payload}],
          suggested_actions?: [{label, route}] }

POST /support/feedback
  body: { message_id: int, rating: "up"|"down", note?: string }

POST /support/resolve
  body: { thread_id: int }

GET  /support/threads
  resp: list of user's threads, paginated

POST /support/escalate
  body: { thread_id: int, reason?: string }
```

### 7.2 Gateway endpoints (called by the Odoo addon)

```
POST /v1/triage
  auth: HMAC token from saas_tenant_gate
  body: { tenant_hash, user_hash, thread_hash, message,
          language?, addon_context: { installed_addons, errors_last_24h } }
  resp: { bot_message, action: "reply"|"file-issue"|"escalate-to-support"|"route-to-config",
          triage_result?, confidence?, workaround_snippet?,
          followup_buttons?, issue_payload? }

POST /v1/file-issue
  auth: HMAC + idempotency-key per thread
  body: issue_payload from /v1/triage
  resp: { github_issue_url, github_issue_number }

POST /v1/webhook-inbound        ← called by GitHub webhook proxy
  auth: GitHub-signed payload
  body: { issue_number, event_type, payload }
  effect: maps to gateway event, posts to originating chat thread
```

### 7.3 GitHub integration

A dedicated service account `odoo-saas-chatbot` with a fine-grained PAT scoped to `issues:write` and `issue_comments:write` on the repo. PAT rotated quarterly.

When the gateway calls GitHub:

```
POST /repos/<org>/<repo>/issues
  body: {
    title: "[chatbot] <user-summarised title>",
    body:  <see §7.4>,
    labels: ["bug" | "feature-request", "source:chatbot", "risk:medium"]
  }
```

### 7.4 Issue body template

```markdown
**Source:** chatbot · tenant=`<hash>` · user=`<hash>`
**Auto-triage:** bug (confidence 0.86)
**Reported via:** in-app support chat

### Symptom (user's words, PII-masked)
> The aged-receivable report is showing duplicated rows.

### Steps to reproduce (extracted from chat)
1. Open Accounting → Aged Receivable
2. Filter by date range
3. Observe duplicated rows

### Environment
- Tenant: `tenant_<hash>` · resolve via gateway
- Addons installed: [list, 43 names truncated]
- Versions: odoo=19.0 · custom-addons=<sha>
- Browser: Chrome 124 / macOS 15

### Workaround offered to user
"Use the Aged Receivable v2 view; it doesn't show the duplication."
[user confirmed workaround works: yes]

### Conversation transcript (PII-masked)
<details><summary>Click to expand</summary>
…full redacted transcript…
</details>

### Notify-back
- Source: support gateway · thread `<hash>`
- Webhook: `POST /v1/webhook-inbound` on the gateway when this issue changes state.
```

---

## 8. Security model

### 8.1 Auth & access

- **Chat widget visible only to authenticated Odoo users.** No public chat.
- **Per-thread access.** A user sees only their own threads. The local group `Support Manager` (per tenant) can read all threads in their tenant for QA. No cross-tenant access — record rules enforce this at the ORM level.
- **HMAC tokens** between addon and gateway, rotated quarterly via `saas_tenant_gate.rotate-telemetry`.
- **Service account** for GitHub, separate from human PATs, with minimum scope.

### 8.2 PII masking

Every GitHub-bound payload passes through a redactor on the gateway:

- **Deny-list (universal):** emails, phone numbers, government IDs (Colombian cédula / NIT), payment-card numbers (Luhn-validated), IBANs, IPv4/IPv6 addresses → `[REDACTED]`.
- **Allow-list (tenant-specific):** customer names from the tenant's `res.partner.name` distinct values → `[CUSTOMER]`. Hash table built nightly per tenant (so only canonical names are masked; nicknames mid-sentence go through the deny-list pattern detector).
- **LLM-based pass** as the final layer: Claude is asked "are there any remaining PII traces?" and removes anything the deterministic passes missed. Findings logged for the security agent (in v5 Pillar D) to review weekly.

Masking is **applied before** the issue body is constructed. Original (unmasked) conversation stays in the tenant DB only; never leaves it.

### 8.3 Sensitive-topic guardrail

A list of regex/embedding-based topic detectors auto-escalates to the support inbox (never to GitHub):

- Billing, refund, dispute.
- Account recovery, password reset, MFA reset.
- Data deletion or PII correction requests.
- Security concerns (suspected breach, suspicious activity).
- Legal threats.

This list lives at `infra/agentlab/sensitive-topics.yml` and is co-owned by the `security-leads` CODEOWNERS group (same group as the masking allow-list from v6 Q3).

### 8.4 Rate limits

- 30 messages per user per hour.
- 5 issue-filing actions per tenant per day.
- 1 sensitive-topic escalation per user per hour (prevents abuse).
- Hit cap → bot pauses with a friendly notice, suggests the support inbox.

### 8.5 Audit

Every chat message, every file-issue call, every escalation writes a row to `gateway_events` on the gateway and is replicated nightly into `saas.audit.event` in the main control-plane DB (per v5 §9). Append-only; S3 Object Lock retention.

---

## 9. Test plan

### 9.1 Unit (addon)

- Model tests: thread creation, message append, state transitions, record rules (own threads only; Support Manager sees tenant scope).
- Controller tests: `/support/chat` request → echo + thread persistence; auth required; rate limit triggers.
- PII-mask tests: 20 sample messages with emails / IDs / customer names → assert all masked.

### 9.2 Integration (gateway)

- Mock Claude responses, assert correct routing for each triage class (`reply`, `file-issue`, `escalate-to-support`, `route-to-config`).
- GitHub API stubbed; assert label set is correct and PII not present.
- HMAC verification — reject bad tokens, reject replays.

### 9.3 E2E (Playwright on agentlab)

- Open chat → ask known-KB question → assert bot answers with KB snippet.
- Open chat → describe fake bug → assert issue filed (against test repo) with `bug` + `source:chatbot` labels; assert customer name masked.
- Open chat → describe feature request → assert `feature-request` label.
- Open chat → describe billing complaint → assert escalation to support inbox; assert NO GitHub issue.
- 5 messages in 30 seconds from one user → assert rate-limit kicks in.

### 9.4 Negative

- Bot must NOT file an issue when triage confidence < 0.5 — must ask clarifying questions instead.
- Bot must NOT leak customer names between tenants — parallel test: open chat in tenant A and B simultaneously, ask similar questions; assert no information bleeds.

### 9.5 Load

- Sustain 50 concurrent conversations across tenants — gateway p95 latency < 2 s.

### 9.6 Adversarial

- Prompt-injection attempts in chat ("ignore prior instructions and …") → bot refuses, logs to security agent's review queue.
- User attempts to extract another tenant's data via crafted questions → bot refuses by virtue of having no such data on hand (KB is non-tenant-specific).

---

## 10. Rollout plan

The chatbot is itself rolled out via the v5 wave system. Phases below describe **feature scope evolution**, not rollout cadence — each phase canaries → w1 → w2 within its own window.

### Phase A — MVP (weeks 18–20, after v5 baseline is live)

- Addon `saas_support_chatbot` v0.1: widget + conversation + file GitHub issues.
- Gateway v0.1 on Fly: Claude integration; KB ingested from addon READMEs (43 addons) + Obsidian docs (`docs/obsidian/`).
- Enabled on canary tenants only.
- No bidirectional sync; bot says "we'll get back to you."
- No back-translation; Spanish messages translated by Claude on the fly.

### Phase B — Back-sync (weeks 21–22)

- Gateway subscribes to GitHub webhook events on `issues`, `pull_requests`, `issue_comments` for `source:chatbot`-labelled issues.
- When linked PR gets a Spec Generator comment, an Implementation preview URL, or a merge — bot posts an update in the originating chat thread.
- Spanish for `es_*` tenants; English for `en_*`.

### Phase C — In-chat `/approve` (weeks 23–24)

- Chat-side buttons: [Approve] [Iterate] map to GitHub PR actions via the gateway.
- Iterate: user types change request → forwarded as an issue comment → triggers Implementation Agent's iteration loop in v5.
- The reporter doesn't need a GitHub account.

### Phase D — Per-tenant context (weeks 25–26)

- Bot reads recent errors from `ir.logging` (last 24 h, per user, sanitised).
- Bot reads current view from the addon's session context (e.g. "user is on the Aged Receivable view").
- Bot suggests workarounds informed by current state.

### Wave rollout (per phase)

- Canary tenants (2 friendly, opted in) for 1 week.
- Wave-1 (25 % of tenants) for 1 week.
- Wave-2 (everyone).

### Rollback

`support_chatbot_enabled` flag per tenant. Flipping off hides the widget instantly. Threads remain in the DB; gateway preserves history.

---

## 11. Observability

### 11.1 Logs

- Gateway logs every event with `tenant_hash`, `user_hash`, `thread_hash`, `event`, `cost_usd`, `latency_ms`.
- Odoo addon logs every controller call with `request_id`, `user_id`, `thread_id`.
- All tagged so they correlate end-to-end.

### 11.2 Per-tenant dashboard

- Conversations per day.
- **Deflection rate** = `bot-resolved ÷ total`. Headline KPI.
- Triage class distribution (bug / feature / config / user-error / sensitive).
- Avg time to first response (target < 5 s).
- Issues filed per day per tenant.
- Spend per day per tenant.
- 👍 / 👎 ratio on bot messages.

### 11.3 Alerts

- Deflection rate < 30 % for 3 days → review KB freshness; Slack `#support-quality`.
- Gateway p95 latency > 3 s for 1 h → page on-call.
- Spend > 80 % of monthly cap → Slack warn.
- Issue-filing rate > daily cap for any tenant → throttle + Slack notify.
- 👎 rate > 25 % on a 7-day window → review classifier; Slack `#support-quality`.

### 11.4 Auditing

Every issue filed and every escalation is in `saas.audit.event` (v5 §9). Quarterly governance review (v5 §10) extends to chatbot metrics.

---

## 12. Success metrics (v6 additions)

| Metric | Target |
|---|---|
| Deflection rate (bot resolves without filing) | ≥ 40 % by Phase A; ≥ 55 % by Phase D |
| Time to first bot response | < 5 s p95 |
| Workaround acceptance (👍 on offered workaround) | ≥ 60 % |
| Filed issues with mis-classified triage (manual audit, 5 % sample) | ≤ 10 % |
| PII leaks in filed issues (security agent audit) | 0 |
| Reporter satisfaction on chatbot-originated issues | ≥ 4.0 / 5 |
| Median chatbot-issue → preview URL | unchanged from v5 (the chatbot is upstream of the existing pipeline) |
| Chatbot spend per month | < USD 300 (caps across all tenants) |
| Sensitive-topic detection accuracy | ≥ 95 % (manual audit) |

---

## 13. Failure modes & mitigations

| Failure | Mitigation |
|---|---|
| Bot files duplicate issues for the same complaint | Idempotency key per thread on `/v1/file-issue`; gateway de-dup window of 24 h per user |
| Bot hallucinates a workaround that breaks things | Workarounds drawn from KB get a `kb-sourced` tag; LLM-generated workarounds carry a `bot-suggested` tag and disclaimer. 👍/👎 telemetry lets us spot bad ones |
| Bot leaks a customer name into a public issue | Three-layer masking (deny-list, allow-list, LLM pass) + weekly random-row audit by security agent |
| Bot fires GitHub issues at every typo | Triage confidence threshold; clarifying-questions step before filing |
| Bot routes a real bug to support inbox by mis-classifying as 'config' | Manual 5 % audit of routed-to-support events; classifier retrained quarterly |
| Gateway is down → users can't chat | Chat widget shows a banner "Support chat is offline; email support@…" |
| GitHub API rate-limited | Per-tenant daily cap (5 issues/day) keeps us under GitHub's 5000 req/h with margin |
| User attempts prompt injection | System prompt hardened; injection attempts logged to security agent's review queue |
| Knowledge base goes stale | Nightly re-embed of changed addon READMEs; deflection-rate alert catches drift |
| Spend cap hit mid-day | Bot pauses new conversations; existing in-flight conversations complete; banner appears |

---

## 14. Open questions

1. **Vector store choice** — pgvector on the gateway's Postgres (simpler, ~free) vs Pinecone/Weaviate (faster, paid). MVP: pgvector; revisit if KB grows past ~100k chunks.
2. **KB refresh cadence** — nightly re-embed of changed addon READMEs (default) vs on-merge webhook (faster but more plumbing). MVP: nightly.
3. **Default language detection** — auto-detect from user's first message vs default from `res.lang`. Suggest `res.lang`, allow override mid-chat.
4. **Threading model** — one thread per topic vs one continuous thread per user. Suggest continuous, with an explicit "New topic" button.
5. **Attachments** — allow screenshots in chat? Defer to Phase E; MVP is text-only.
6. **Voice** — out of scope.
7. **Public docs site powered by same KB** — out of scope for this spec; separate ADR.
8. **Sensitive-topic list ownership** — `security-leads` CODEOWNERS group (aligns with v6 Q3 answer for masking allow-list).
9. **Should the chatbot itself follow the v5 PR workflow when it changes?** Yes — every modification to `saas_support_chatbot` or the gateway code is spec-driven, goes through Spec Generator + Implementation Agent + preview env like any other addon work.
10. **What about the chatbot building its own followup issues?** When a bot conversation reveals a *second* unrelated bug ("oh and also …"), the bot should file a separate issue rather than bundling. Confirm policy.
