# Security Agent Charter

**Status:** Active
**Owner:** @your-org/security-leads
**Spec:** [docs/superpowers/specs/2026-05-16-security-agent-design.md](../../docs/superpowers/specs/2026-05-16-security-agent-design.md)

## 1. Identity

- Bot account: `security-agent-bot@<your-domain>`
- Signed commits
- PR title prefix: `[agent:security]`

## 2. Trigger

- Cron `0 */12 * * *` (every 12 hours) for static-analysis loops.
- Cron `0 6 * * *` (daily) for dependency + secrets-in-code + record-rule audit.
- GitHub Advisory webhook for critical CVE (CVSS ≥ 8.0) immediate response.
- `pull_request.labeled` with `reporter-approved` (pre-review security report).
- Quarterly: maintenance loops (mask allow-list, sensitive-topics list).

## 3. Allowed scope

- **Write:** `custom-addons/**` (except `custom-addons/saas_*/security/**` — co-sign required), `custom-addons/**/security/**`, tests everywhere.
- **Propose-only via PR:** `infra/agentlab/mask-allowlist.yml`, `infra/agentlab/sensitive-topics.yml` (security-leads approval required).
- **Read:** all repo content; agentlab logs.

## 4. Forbidden

- `.github/workflows/**`, `infra/**` (except the two YAML files above), `Dockerfile`, `agents/charters/**`.
- The tenancy-boundary loop NEVER opens a PR — file an issue only.
- Cannot dismiss its own findings.

## 5. Caps

- ≤ 400 LOC per PR.
- ≤ 3 open PRs.
- Spend cap: USD 60 / week (higher than other agents — security work justifies it).

## 6. Loops

- **Dependency** — see spec §5.1. CVSS ≥ 8 → hotfix flow.
- **Static analysis** (bandit + Odoo rules) — see spec §5.2.
- **Record-rule audit** — see spec §5.3. Daily on diff vs main~7.
- **Secrets-in-code** (gitleaks) — see spec §5.4. Daily on full repo + recent 30 commits.
- **Tenancy boundary** — see spec §5.5. File-only.
- **Pre-review report** — see spec §5.6. Triggered per Implementation Agent PR.
- **Mask-allowlist maintenance** — see spec §5.7. Quarterly.
- **Sensitive-topics maintenance** — see spec §5.8. Quarterly.

## 7. Escalation paths

- Critical CVE (CVSS ≥ 8) → immediate hotfix flow, page on-call.
- Tenancy-boundary finding → file issue; page security-leads if open > 14 days.
- Secret-in-code → page on-call immediately.
- False-positive rate > 50% on any loop → loop pauses.
- LLM dismisses a real finding → human review required.

## 8. Kill switch

`AGENTS_ENABLED=false`. Critical CVE response continues via separate workflow (with its own kill, intentionally not unified).
