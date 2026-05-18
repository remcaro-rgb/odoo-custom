# Support Triage Agent Charter

**Status:** Active
**Owner:** @your-org/security-leads + @your-org/agent-team
**Spec:** [docs/superpowers/specs/2026-05-16-support-triage-agent-design.md](../../docs/superpowers/specs/2026-05-16-support-triage-agent-design.md)

This is the **customer-facing** agent. Different bucket from the five engineering agents. Lives inside the Odoo app as a chat widget; talks to a Fly gateway.

## 1. Identity

- Bot account in GitHub: `support-triage-bot@<your-domain>` (for the issues it files).
- Service account in Odoo: `support_chatbot_service` (the gateway authenticates as this).
- Service-account GitHub PAT scoped to `issues:write` + `issue_comments:write` only.

## 2. Trigger

- End-user opens the chat widget in their Odoo tenant (per-tenant feature flag `support_chatbot_enabled` must be true).
- GitHub webhook events (issues + PRs labelled `source:chatbot`) for bidirectional back-sync.

## 3. Allowed scope

- **In tenant:** read/write its own `saas.support.thread` and `saas.support.message` tables; read tenant's installed addons via `saas_tenant_gate`.
- **In GitHub:** open issues with labels `bug | feature-request` + `source:chatbot`; comment on issues it filed; never on other issues.
- **In gateway:** the KB (read), `gateway_events` (write), `reporter_identity` (write).

## 4. Forbidden

- **Never** sends content to GitHub without three-layer PII masking.
- **Never** files for a "sensitive" classification (billing, account recovery, security, legal) — routes to support inbox instead.
- **Never** acts on behalf of one tenant inside another tenant's data.
- **Never** approves a PR (it can map `/approve` from chat → GitHub `/approve` only on a PR the user is the linked reporter of).

## 5. Caps

- 30 messages / user / hour.
- 5 issues filed / tenant / day.
- 1 sensitive-topic escalation / user / hour (anti-abuse).
- Spend cap: USD 300 / month total across all tenants.
- Confidence threshold: ≥ 0.5 to file an issue; lower triggers clarifying questions.

## 6. Sequences

- **Resolve-in-chat** — KB answers; counts toward deflection rate; no issue.
- **Triage → file** — classifier + workaround + PII mask + GitHub `POST /issues`.
- **Triage → escalate** — sensitive topics to support inbox.
- **Bidirectional sync** — GitHub webhooks → chat thread updates.
- **In-chat /approve** (Phase C+) — map to GitHub PR `/approve`.

## 7. Escalation paths

- Sensitive topic → support inbox (never GitHub).
- Confidence < 0.5 → ask clarifying questions.
- PII detected in masked output (LLM third pass) → log to security audit queue; don't file.
- Rate limit hit → friendly pause notice to user; suggest support inbox.
- Prompt injection in chat → refuse; log to security audit.

## 8. Kill switch

Per-tenant feature flag `support_chatbot_enabled` on `saas_tenant_gate`. Flipping off hides the widget; threads remain in DB.

Org-wide: `AGENTS_ENABLED=false` doesn't disable this agent directly (it's a customer-facing service), but does disable issue-filing actions to GitHub. In-flight chats continue with KB-only answers and inbox-escalation paths.
