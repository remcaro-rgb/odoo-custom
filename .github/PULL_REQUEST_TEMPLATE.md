<!--
PR template — odoo-saas
The spec-required CI check will read the "Spec:" line below and fail the build
if it's missing or doesn't point at a real file (unless the PR has the
`spec-exempt` label applied by a repo admin).
-->

## Spec

Spec: docs/superpowers/specs/YYYY-MM-DD-<slug>-design.md
<!-- or -->
<!-- Spec: docs/superpowers/specs/YYYY-MM-DD-<slug>-fix.md -->

## Summary

<!-- 2–3 sentences. What changes and why. Don't repeat the spec. -->

## Risk classification

- [ ] `risk:low` — comment/doc edits, dependency bumps that pass tests, formatting
- [ ] `risk:medium` — typical addon changes, schema-additive migrations
- [ ] `risk:high` — `saas_tenant_gate`, security/, destructive schema changes, infra
- [ ] `risk:critical` — control-plane logic, tenancy boundary

<!--
Auto-detected via touched paths; you can downgrade with a comment justifying.
Soak time before prod promotion: low/medium=24h, high=72h.
-->

## CODEOWNERS checklist *(required before `human-review-approved`)*

- [ ] Spec's tenancy-impact section is accurate for what was actually built.
- [ ] Tests cover the new behaviour AND a negative case.
- [ ] No regression in `addon-upgrade-matrix`.
- [ ] *(v5)* All human commits on this branch have a reporter ping comment on the issue, and the reporter either `/approved` after the last one or 24h silence elapsed. *(only applies on `agent/spec-*` branches)*
- [ ] Security agent's pre-review report is clean OR findings are noted/dismissed with reason.

## Tests / verification

<!--
What did you run? What did you observe? Paste relevant excerpts.
- `pytest custom-addons/<addon>/tests/`
- Agentlab manual check at <URL>
- Playwright critical-path: ...
-->

## Rollout

- [ ] Default flow (wave canary → w1 → w2 via `promote-to-prod`)
- [ ] Hotfix (severity ≥ high; requires N=2 prod-deployers approval; retro fix-brief in 48h)
- [ ] Documentation-only (no rollout impact)

## Related

- Issue: #
- Linked spec PR: #
- Predecessor spec or ADR: #
