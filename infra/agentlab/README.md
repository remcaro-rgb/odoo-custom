# infra/agentlab

Configuration + scripts for the **agentlab** environment — the daily-refreshed
masked clone of staging that AI agents work against.

See: `docs/superpowers/specs/2026-05-16-agentlab-environment-design.md`.

## Files

- `mask-allowlist.yml` — columns explicitly safe to leave **unmasked**. Everything else is masked by default.
- `sensitive-topics.yml` — topic patterns that route to the support inbox instead of GitHub. Owned by `security-leads`.
- `mask_prod_data.py` — the masking pipeline. Reads `mask-allowlist.yml` + `masking-rules.yml`; classifies each column (Odoo `ir_model_fields` ttype, falling back to `information_schema`); applies set-based SQL masking; runs the deny-list pass; validates with a sample audit. Pure helpers unit-tested in `tests/test_masking.py`.
- `masking-rules.yml` — per-column-type masking strategies (hash, redact, fake-replace).

## Ownership

All files in this directory are owned by `@your-org/security-leads`. CODEOWNERS
enforces this. Any PR touching this directory requires 2 security-leads approvals.

## Audit

Weekly random-row audit (Security Agent's job per its design spec §5.7):
sample 100 random rows from agentlab; assert no PII pattern matches.
Findings → page security-leads.
