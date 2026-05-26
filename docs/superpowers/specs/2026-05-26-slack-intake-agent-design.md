# Slack Intake Agent — Design Spec

**Date:** 2026-05-26
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** New `slack_intake` agent + supporting ports, adapters, FastAPI service, and Fly app — bridges team Slack into the Spec Generator flow per parent plan §Q7.

---

## 1. Goal

Make Slack a first-class intake channel for the Spec Generator. Team members invoke `/intake` in a Slack channel, fill a Block-Kit modal, and a GitHub issue is filed with `feature-request` or `bug` + `source:slack` labels. The existing Spec Generator workflow picks it up unchanged. The bot relays Spec Generator's clarifying comments back into the originating Slack thread, syncs the reporter's Slack replies back as attributed GitHub issue comments, and exposes a "Confirm intent ✓" button that fires `/confirm` on the issue. Once intent is confirmed (Slack button, GitHub `/confirm` comment, or 24h silence), conversation hands off to GitHub for the Implementation Agent stage.

Outcome: the team's primary chat surface becomes a valid Spec Generator entry point. Reporters never have to context-switch into GitHub during the intent-confirmation loop.

## 2. Non-goals

- `/confirm` / `/approve` slash commands for the Implementation Agent stage. (Plan §Q7 mentions this; out of scope here — the bot exits after intent-confirmed.)
- Customer-facing Slack intake. External users are covered by `saas_support_chatbot` (§5.10 of the parent plan).
- Multi-tenant Slack workspaces. One internal workspace is assumed.
- Replacing the Zapier hook used elsewhere. This agent owns intake only.
- A full Teams / Discord port. The hexagonal design makes that a future adapter swap, not a current goal.

## 3. Tenancy impact

**No impact on per-tenant data isolation.** The bot operates entirely on:

- The internal team Slack workspace (no customer messages).
- The GitHub repo (issues + comments only; no per-tenant DB access).
- Its own SQLite state on a Fly volume (thread↔issue mapping, Slack↔GitHub user mapping, webhook delivery dedupe — none of which contains tenant data).

The bot does NOT:

- Read or write any tenant Postgres DB.
- Touch `saas_tenant_gate`, seat caps, telemetry, or feature flags.
- Access the agentlab masked snapshot or any production tenant data.
- Touch the per-tenant migration queue.

Cross-tenant leak risk: zero — no per-tenant data passes through the bot. The only message content it handles is what a team member typed into `/intake` or a GitHub comment by `spec-generator-bot`, both of which the team-internal Slack workspace would already be authorized to see.

## 4. Data model changes

No Odoo model changes. The bot stores state in a SQLite file at `/data/slack_intake.db` on a Fly volume. Three tables:

```sql
CREATE TABLE thread_issue (
    slack_channel       TEXT NOT NULL,
    slack_thread_ts     TEXT NOT NULL,
    github_repo         TEXT NOT NULL,
    github_issue_number INTEGER NOT NULL,
    reporter_slack_id   TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_relayed_comment_id INTEGER,
    intent_confirmed_at TIMESTAMP,
    PRIMARY KEY (slack_channel, slack_thread_ts)
);
CREATE INDEX idx_thread_issue_gh ON thread_issue (github_repo, github_issue_number);

CREATE TABLE user_mapping (
    slack_user_id  TEXT PRIMARY KEY,
    github_login   TEXT NOT NULL,
    linked_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    linked_method  TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE dedupe (
    key      TEXT PRIMARY KEY,
    seen_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

No migration plan needed — first deploy creates the tables via `CREATE TABLE IF NOT EXISTS`. The schema lives in [agents/agents/adapters/state_sqlite.py](../../../agents/agents/adapters/state_sqlite.py).

Two new ports added to the agent runtime (`agents/agents/ports/`):

- `ChatOps` — thread-aware messaging ops (post, reply, edit, react, modal). Distinct from `Notifier` which stays severity-based.
- `StateStore` — persistent state with three operation groups (thread↔issue link, user mapping, dedupe).

## 5. API surface

### Inbound HTTP (FastAPI service, hosted on Fly app `odoo-saas-slack-intake`)

| Endpoint | Method | Caller | Purpose |
|---|---|---|---|
| `/healthz` | GET | Fly probe | Liveness check |
| `/slack/commands` | POST | Slack | `/intake` slash command — opens modal |
| `/slack/interactivity` | POST | Slack | Modal submit + button clicks |
| `/slack/events` | POST | Slack | Channel/thread message events |
| `/github/webhook` | POST | GitHub | `issue_comment.created` |

Signature verification (Slack v0 HMAC, GitHub HMAC-SHA256) happens in the EventBus adapters before any business logic. Replay protection is via the `dedupe` table.

### Outbound calls

| Service | API | Used for |
|---|---|---|
| Slack `chat.postMessage` | post a top-level message + the thread-root confirmation | Path A |
| Slack `chat.postMessage` (with `thread_ts`) | post Spec-Generator comments into the thread | Path B |
| Slack `chat.update` | edit the relayed card to show "✅ Intent confirmed" | Path D |
| Slack `chat.postEphemeral` | refuse sensitive intake; warn unauthorized clickers | Path A, D |
| Slack `views.open` | open the `/intake` modal | Path A |
| Slack `reactions.add` | 👀 delivery receipt on relayed Slack replies | Path C |
| GitHub `POST /repos/{repo}/issues` | open the issue | Path A |
| GitHub `POST /repos/{repo}/issues/{n}/comments` | reporter reply + `/confirm` | Path C, D |

### Block Kit templates

- [agents/agents/templates/intake_modal.json](../../../agents/agents/templates/intake_modal.json) — title / description / kind (bug|feature) / severity / optional addon
- [agents/agents/templates/relay_card.json](../../../agents/agents/templates/relay_card.json) — relayed comment + "Confirm intent ✓" + "Open on GitHub ↗"

## 6. Security model

### Tenancy-isolation argument

The bot handles only team-internal Slack and the public GitHub repo. It has no read or write access to any tenant Odoo DB, no access to the agentlab masked snapshot, and no awareness of `saas_tenant_gate`. The state SQLite holds thread↔issue mappings and Slack↔GitHub user IDs — neither category contains tenant data. There is therefore no plausible data-flow path by which one tenant's information could appear in another tenant's workspace via this bot.

### Authn / authz

- **Slack signature verification** — strict v0 HMAC against `SLACK_SIGNING_SECRET`, 5-minute freshness window, no exceptions. Implemented in [agents/agents/adapters/events_slack_webhook.py](../../../agents/agents/adapters/events_slack_webhook.py).
- **GitHub webhook verification** — HMAC-SHA256 against `GITHUB_WEBHOOK_SECRET`. Implemented in [agents/agents/adapters/events_github_webhook.py](../../../agents/agents/adapters/events_github_webhook.py).
- **GitHub PAT** — service-account, fine-grained, scoped `issues:write` + `issue_comments:write` + `metadata:read`. Matches the Support Triage Agent's posture (§5.10 of the parent plan).
- **Slack scopes** — minimum viable: `commands`, `chat:write`, `chat:write.public`, `channels:history`, `groups:history`, `im:history`, `users:read`, `users:read.email`, `reactions:write`.

### Sensitive data handling

- **PII mask** — cheap two-stage mask (email regex, phone regex) before content lands in either GitHub or Slack. Phase B upgrades to the 3-layer chain shared with the Support Triage Agent (deny-list → tenant allow-list at `infra/agentlab/mask-allowlist.yml` → LLM cleanup pass).
- **Sensitive-topic detector** — `agents.slack_intake.sensitive_patterns` regex list. Matches refuse the intake and route the reporter to the support inbox; nothing is filed on GitHub. Default list covers billing / security / legal / account-recovery keywords.
- **Reporter impersonation** — `/confirm` button verifies clicker matches the original reporter on the `thread_issue` row. Unauthorized clickers get an ephemeral warning, no GitHub comment is posted.

### Rate limits + kill switch

- 5 issues / user / hour, 30 issues / workspace / hour (mirrors §5.10 caps).
- Channel allow-list (`agents.slack_intake.allowed_channels`) defaults to `[]` — fail closed, no channel is permitted until ops adds it.
- `AGENTS_ENABLED` repo variable (existing) gates new deploys; the same flag exposed as a Fly secret causes the running service to return 503 on every webhook.

## 7. Test plan

Test count gates: the agent-guardrails CI check forbids the test count from shrinking. This change adds **47** tests covering the four paths and the new ports.

- **Unit / contract** (under `agents/tests/contract/`):
  - `test_state_sqlite.py` — round-trip, idempotent insert, intent-confirm marker, user-map replace, dedupe TTL.
  - `test_events_slack_webhook.py` — signature verify (fresh, stale, tampered, missing), URL-handshake, slash-command publish, modal-submit publish, message event publish, invalid-sig 401.
  - `test_events_github_webhook.py` — valid sig routing, invalid sig 401, missing sig 401, unrelated-event routing.
- **Integration** (`agents/tests/integration/test_slack_intake_flow.py`):
  - Path A: modal opens in allowed channel; blocked in unlisted channel (ephemeral message); modal submission creates issue + thread root; sensitive topic refused with `response_action: errors`.
  - Path B: Spec-Generator comment relays to thread; relay skipped after intent-confirmed; unrecognised author ignored; duplicate `delivery_id` deduped; **shadow_mode=true short-circuits the relay** (Phase B gate).
  - Path C: Slack reply relays to GitHub with attribution; relay skipped after intent-confirmed; bot messages ignored; top-level (non-thread) messages ignored.
  - Path D: Confirm button posts `/confirm`, marks `intent_confirmed_at`, edits the card; only the original reporter may confirm.
- **Adversarial**:
  - Slack signature: stale timestamp (>5min), tampered body, missing header.
  - GitHub signature: missing X-Hub-Signature-256, mismatched HMAC.
  - Out-of-allow-list channel returns ephemeral, no modal opens.
  - Sensitive content in description triggers refusal without posting anywhere.
- **E2E (manual, post-deploy)**: end-to-end smoke against `#intake-test` per the runbook at [docs/runbooks/slack-intake-rollout.md](../../runbooks/slack-intake-rollout.md). Phase B verifies issue creation only; Phase C verifies the full relay.

CI: `.github/workflows/deploy-slack-intake.yml` runs `ruff check` + `pytest tests/` on every push touching `agents/**` or `infra/fly/slack-intake/**`. Deploy is gated on the test job passing.

## 8. Rollout plan

Four phases per the parent plan §Q7 and the runbook:

| Phase | Scope | Gating |
|---|---|---|
| **A** | Land code on `feat/slack-intake-phase-a`. Pure code change, no infra. | Tests green + lint clean. |
| **B** | Stand up `odoo-saas-slack-intake` Fly app with `shadow_mode = true`. Bot creates issues but does NOT relay GH → Slack. | One-week soak watching issue-body quality + `/intake` UX. |
| **C** | Flip `shadow_mode = false`, restrict to one channel (`#intake-test`). | One-week soak watching relay loop, button click-through, and any PII leak signals. |
| **D** | Expand `allowed_channels` workspace-wide. | Announce in `#announcements`. |

Feature flags / kill switches:

- `agents.slack_intake.shadow_mode` (config, also via `AGENTS_AGENTS_SLACK_INTAKE_SHADOW_MODE` env var on Fly).
- `agents.slack_intake.allowed_channels` (default `[]`; the agent fail-closes if a channel isn't listed).
- `AGENTS_ENABLED` repo variable (existing) gates the deploy workflow; same name as a Fly secret 503s the running service.

Migration cost: zero — no per-tenant DB touched, no Odoo addons changed.

Rollback path:

1. Soft pause: `gh variable set AGENTS_ENABLED -b false` → deploy workflow refuses; existing Fly service unchanged.
2. Hard pause: `flyctl secrets set --app odoo-saas-slack-intake AGENTS_ENABLED=false` → service returns 503 on every webhook within ~1 min.
3. Full takedown: `flyctl apps destroy odoo-saas-slack-intake` (state in the Fly volume is lost — fine, it's all reconstructible from GitHub issues + Slack history).

Decision tree for in-flight rollback in the rollout runbook at [docs/runbooks/slack-intake-rollout.md](../../runbooks/slack-intake-rollout.md).

## 9. Observability

### Logs (stdjson via the existing Logger port; Fly forwards to Better Stack)

Span structure: every Path emits `<path>.<step>` entries. Key events:

- `slack_intake.modal_opened` — Path A enters
- `slack_intake.issue_created` — Path A success; carries `issue`, `channel`, `thread_ts`
- `slack_intake.sensitive_blocked` — Path A refuse; carries `user`
- `slack_intake.channel_not_allowed` — Path A denial; carries `channel`
- `slack_intake.relayed_to_slack` — Path B success; carries `issue`, `author`
- `slack_intake.shadow_mode_skip_relay` — Path B no-op due to shadow mode
- `slack_intake.relay_skipped_post_confirm` — Path B no-op after intent confirmed
- `slack_intake.duplicate_delivery` — Path B dedupe hit
- `slack_intake.relayed_to_github` — Path C success
- `slack_intake.intent_confirmed` — Path D success

### Metrics watched (manual, weekly during rollout — auto-dashboarded in Phase 9 of the parent plan)

- Median time `/intake` modal submit → GitHub issue created (target < 5 s)
- Median time Spec Generator comment → Slack thread reply (target < 30 s)
- Median time reporter Slack reply → GitHub comment (target < 30 s)
- `/intake` modal abandonment rate (target < 25 %)
- 24h `intent-confirmed` rate from Slack-filed issues (target ≥ 70 %)
- Issues filed via Slack vs. native GitHub (sanity, no target)
- Sensitive-topic refusals routed to support inbox (sanity, no target)

### Alerts

- `slack_intake.*.error` rate > 0 over 5 min → page-on-call (info channel during shadow mode).
- `/healthz` failures from Fly probe → existing Fly auto-restart + Better Stack heartbeat.
- Slack signature verification failure rate > 0 over 5 min → security alert (possible token leak or replay attack).

### Audit

Every issue created via `/intake` carries a `Filed via Slack /intake by @<user> (<slack_id>)` line in the issue body, so the GitHub audit trail is self-describing. No separate audit table.

## 10. Open questions

1. **User mapping seed**: should the deploy script auto-seed `user_mapping` from Slack workspace member emails matched against GitHub org members' verified emails, or always prompt on first `/intake`? Trade-off: auto-seed risks stale mappings if users change their Slack/GitHub emails after a rename.
2. **`/intake list` companion command**: do we want a way for users to list their open intake-filed issues? Defer to v2 unless Phase C feedback raises it.
3. **Post-confirm preview URL relay**: after intent-confirmed, should the bot post a one-shot "🚀 Implementation Agent is building — preview URL incoming" notice to the Slack thread when the Impl Agent picks up the issue? Nice-to-have; requires subscribing to a different GitHub event (`issues.labeled` for `intent-confirmed`). Recommend deferring to a v1.1.
4. **Teams parity**: do we want to mirror this for Microsoft Teams during the same rollout window, or wait for explicit demand? The hexagonal design makes it a ~1-week port, but ops cost doubles.
5. **Phase B shadow-mode auto-exit**: should `shadow_mode = true` auto-expire after N days as a forcing function, or stay until ops explicitly flips it? Bias toward explicit-flip — surprise rollouts are worse than slow ones.

---

**Implementation artifacts:**

- Agent core: [agents/agents/slack_intake/core.py](../../../agents/agents/slack_intake/core.py)
- Adapters: `agents/agents/adapters/{events_slack_webhook,events_github_webhook,issues_github,state_sqlite,state_memory,notifier_slack}.py`
- HTTP service: [agents/agents/services/slack_intake_http.py](../../../agents/agents/services/slack_intake_http.py)
- Fly app: `infra/fly/slack-intake/`
- CI deploy: [.github/workflows/deploy-slack-intake.yml](../../../.github/workflows/deploy-slack-intake.yml)
- Tests: `agents/tests/contract/test_*.py` + `agents/tests/integration/test_slack_intake_flow.py`
- Rollout runbook: [docs/runbooks/slack-intake-rollout.md](../../runbooks/slack-intake-rollout.md)
