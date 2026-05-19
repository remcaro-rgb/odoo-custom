# Contributing to odoo-custom

This repository follows the spec-driven development workflow defined in
[`docs/2026-05-15-spec-driven-dev-plan.md`](docs/2026-05-15-spec-driven-dev-plan.md).

## Writing a spec

Every non-trivial change starts with a spec or fix-brief, committed under
`docs/superpowers/specs/`:

- **New features →** copy [`docs/superpowers/specs/_TEMPLATE-design.md`](docs/superpowers/specs/_TEMPLATE-design.md)
- **Bug fixes →** copy [`docs/superpowers/specs/_TEMPLATE-fix.md`](docs/superpowers/specs/_TEMPLATE-fix.md)
- **Implementation steps →** copy [`docs/superpowers/plans/_TEMPLATE.md`](docs/superpowers/plans/_TEMPLATE.md)

Name your file `YYYY-MM-DD-<slug>-design.md` (or `-fix.md` / plain `<slug>.md`
for plans).

## Linking a spec from a PR

Add a line in the PR body:

```
Spec: docs/superpowers/specs/2026-05-19-my-feature-design.md
```

The `spec-required` CI check enforces that every PR touching
`custom-addons/`, `infra/`, `.github/workflows/`, or `Dockerfile` carries a
spec link. Use the `spec-exempt` label only for true exemptions (typo fixes,
README tweaks); exemptions are audited.

## ADRs

Architectural decisions go under [`docs/adr/`](docs/adr/README.md) using the
numbered-record format. Open a discussion before the ADR if the decision is
contentious.

## Agent-authored PRs

PRs on `agent/spec-*` branches are subject to the `agent-guardrails` CI gate:
≤ 400 LOC, no edits under `infra/` or `.github/workflows/`, signed commits,
test count must not shrink. The kill switch is the repo variable
`AGENTS_ENABLED` — set to `false` to halt all agent CI immediately.

## Pre-commit hooks

YAML and GitHub Actions workflow files are linted on every PR by
`.github/workflows/lint-workflows.yml`. To catch issues locally before
pushing:

```bash
pip install pre-commit
pre-commit install            # one-time, installs the git hook
pre-commit run --all-files    # ad-hoc full-repo scan
```

The hook config lives in [`.pre-commit-config.yaml`](.pre-commit-config.yaml)
and runs `yamllint` (with [`.yamllint.yml`](.yamllint.yml)) and
`actionlint`.

## Code review

CODEOWNERS auto-requests review on every PR. See [`.github/CODEOWNERS`](.github/CODEOWNERS)
for the ownership map. The PR template's CODEOWNERS checklist must be ticked
before merge.
