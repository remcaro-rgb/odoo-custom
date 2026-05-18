# <Title> — Design Spec

**Date:** YYYY-MM-DD
**Author:** <name>
**Status:** Draft | In Review | Accepted | Superseded
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** <one-line summary of what artifacts this spec governs — new addon, infra change, etc.>

---

## 1. Goal

One paragraph. What outcome does this produce? Who benefits and how?

## 2. Non-goals

Bullet list. What this spec explicitly does NOT cover. The job of non-goals is to prevent scope creep.

- ...

## 3. Tenancy impact

Mandatory section — cannot be empty. The spec-quality CI check fails if this is missing or trivially short.

Answer at minimum:

- Does this touch the per-tenant boundary?
- Does it require a migration on every tenant DB?
- Does it change `saas_tenant_gate` seat caps, telemetry, or feature flags?
- Could a tenant's data leak across the boundary as a result of this change?

If the answer is "no impact" — say so explicitly and justify why.

## 4. Data model changes

New models, fields, indexes, constraints. Include sample SQL or Python ORM declarations.

```python
class NewModel(models.Model):
    _name = 'your.model'
    # ...
```

If schema migrations are required, call out the migration plan here (see also: §8 Rollout).

## 5. API surface

New/changed:

- Controllers and routes
- RPC methods
- JSON endpoints
- Webhook payloads

Include example request/response payloads where they aid clarity.

## 6. Security model

- Record rules — who can read/write which records?
- Groups and ACLs — what permissions are required?
- Sensitive data — what's exposed to which role?
- **Tenancy-isolation argument** — one paragraph: how does this NOT leak across tenants?

## 7. Test plan

What unit, integration, and E2E tests gate this change. Include negative tests.

- Unit: ...
- Integration: ...
- E2E (Playwright on agentlab): ...
- Adversarial: ...

For fix-briefs, the regression test that would have caught the bug.

## 8. Rollout plan

- Feature-flagged? Via which flag?
- Which wave first (canary / w1 / w2)?
- Migration cost estimate (rows touched × cost per row, if applicable)?
- Rollback path — what's the recovery if this goes wrong?

## 9. Observability

What new logs, metrics, or alerts does this need?

- Logs: tags / fields added
- Metrics: counters, gauges, histograms
- Alerts: thresholds + channels

## 10. Open questions

List with at least one question. The spec-quality CI check fails if a design spec has zero open questions — we don't trust artifacts that "have no questions."

1. ...
