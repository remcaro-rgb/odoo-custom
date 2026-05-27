# Spec Generator — rollout runbook (PR1 → PR4 → live)

**Owner:** DevOps + this week's rotation.
**Parent strategy:** [docs/2026-05-15-spec-driven-dev-plan.md §5.3](../2026-05-15-spec-driven-dev-plan.md)
**Design spec:** [docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md](../superpowers/specs/2026-05-16-spec-generator-agent-design.md)

PR1–PR4 (this rollout) put the Spec Generator agent's runtime impl in `agents/agents/spec_generator/`. It runs on GitHub Actions (`.github/workflows/spec-generator*.yml`), NOT on a long-running Fly app — there is no service to deploy, only a `pip install` in the workflow + repo variables + secrets.

Kill switch through the whole rollout: the `AGENTS_ENABLED` repo variable. Set it to `false` to short-circuit every spec-generator workflow run.

---

## Phase 1 — Shadow on the data-plane repo

**Goal:** the agent parses every routed issue and runs the drafter, but does NOT push branches, open PRs, or comment. The team validates classification quality + drafted-spec quality from the workflow logs.

### Bootstrap

```bash
# 1. Confirm the workflows are deployed to the data-plane repo. They live
#    here (in the agents/ source repo) and must be copied to .github/workflows/
#    of the DATA-PLANE repo (the one issues are filed against). The header
#    comment in each workflow file explains why.

# 2. Set the kill switch ON.
gh variable set AGENTS_ENABLED --body "true" --repo <data-plane-repo>

# 3. Pin the agent ref the workflow installs from.
gh variable set AGENT_REF --body "main" --repo <data-plane-repo>

# 4. Set the shadow flag in config.prod.yml (or via env override).
#    agents:
#      spec_generator:
#        shadow_mode: true

# 5. Trigger a smoke: file a labelled feature-request and watch the
#    spec-generator.yml run. Confirm in the logs:
#      - spec_generator.intake
#      - spec_generator.draft.start / .end
#      - spec_generator.shadow_mode_skip_write  ← stops here
```

### Verification checklist (Phase 1)

- [ ] `spec_generator.intake` event emitted for the test issue with the right `classification`.
- [ ] The drafter ran to completion (no LLM error).
- [ ] `shadow_mode_skip_write` is the LAST event — no push, no PR open, no comment.
- [ ] For a bug intake: `spec_generator.bug_repro` fired with one of the three outcomes.
- [ ] For a sensitive intake: no draft, the Slack notifier ping fired.

### Soak

One week minimum, AT LEAST 10 issues across feature + bug + sensitive.

---

## Phase 2 — Single-repo, single-label

**Goal:** flip the agent live, but ONLY for issues carrying a dedicated `spec-gen-test` label so the team can opt traffic in.

### Flip

```bash
# 1. Drop shadow_mode.
#    agents:
#      spec_generator:
#        shadow_mode: false
#        # Optional: restrict the rollout to one label until Phase 3.
#        routing_labels:
#          - spec-gen-test
#    (Note: routing_labels filtering lives in the workflow's `if:` guard
#    today, not in the agent code — bump the workflow guard to
#    `contains(..., 'spec-gen-test')` for this phase.)

# 2. Deploy the spec-generator-bot GitHub App if you haven't already.
#    Install on the org, set repo permissions:
#        Contents: Read & Write
#        Issues: Read & Write
#        Pull requests: Read & Write
#        Metadata: Read
#    Configure the App ID + private key:
gh variable set SPEC_GENERATOR_BOT_APP_ID --body "<app-id>"
gh secret set SPEC_GENERATOR_BOT_PRIVATE_KEY < private-key.pem

# 3. File a real issue labelled `feature-request` + `spec-gen-test`.
#    Watch for:
#      - branch `agent/spec-<N>` created
#      - PR `[agent:spec-generator] spec: <slug>` opened
#      - PR labels: spec-drafted, awaiting-reporter-confirm
#      - Comment on the issue with the PR URL + open questions
#      - For bugs: PR also carries `repro:<outcome>` label
```

### Verification checklist (Phase 2)

- [ ] Branch `agent/spec-<N>` exists with one commit by `spec-generator-bot`.
- [ ] PR opens with `Spec: docs/superpowers/specs/<file>.md` in the body (gates the spec-required check).
- [ ] PR opens with `spec-drafted` + `awaiting-reporter-confirm` labels.
- [ ] Issue comment links to the PR and contains numbered open questions.
- [ ] Reporter reply triggers `spec-generator-iterate.yml`; the spec branch gets a follow-up commit.
- [ ] Reporter `/confirm` flips `intent-confirmed` on the PR within ~30s.
- [ ] The 24h sweep (`spec-generator-sweep.yml`) runs (use `workflow_dispatch` for an early smoke). With `dry_run=true` it emits `sweep-decision` events; with `dry_run=false` it confirms eligible PRs.

### Soak

One week, AT LEAST 5 confirmed flows.

---

## Phase 3 — Default-on for `feature-request`

**Goal:** route every new `feature-request` through Spec Generator. Keep `bug` opt-in for another week.

### Flip

```bash
# Just drop the routing_labels override from config — the workflow
# already runs on every issues.opened|labeled with the routing labels.
```

### Verification checklist (Phase 3)

- [ ] Daily volume matches expectations (≤ N issues/day; check the AGENTS_AGENTS_SPEC_GENERATOR_MAX_OPEN_PRS cap is not being hit).
- [ ] No human-triage backlog growing (the team is keeping up with `/confirm`).
- [ ] Drafted-spec quality stays high (no template-completeness failures from spec-quality.yml).
- [ ] Slack relay (via Phase D of the slack-intake bot) carries comments + confirm prompts back to the originating thread.

### Soak

Two weeks minimum before flipping bugs on.

---

## Phase 4 — Default-on for `bug` (with heuristic repro)

**Goal:** route every new `bug` through Spec Generator. The heuristic repro classifier (PR4) labels each PR `repro:repro-confirmed`, `repro:needs-repro-info`, or `repro:needs-fixture`.

### Flip

```bash
# Nothing in the agent or workflow changes — the routing label `bug`
# already triggers spec-generator.yml. This phase is just the soak
# threshold from Phase 3 being met.
```

### Verification checklist (Phase 4)

- [ ] PRs labelled `repro:needs-fixture` are picked up by security-lead within 24h.
- [ ] PRs labelled `repro:needs-repro-info` get reporter clarification (or auto-close after 7 days of silence).
- [ ] PRs labelled `repro:repro-confirmed` go through the normal iterate / sweep flow.

### Deferred — full agentlab repro shim

The actual Playwright-on-agentlab repro is a follow-up:
> **Backlog issue:** "Spec Generator: bug-repro on agentlab" — when present, replaces the heuristic for `repro-confirmed` candidates with a real Playwright pass that attaches logs + screenshots to the PR. Until then the heuristic is the final word.

---

## Rollback

The kill switch is the `AGENTS_ENABLED=false` repo variable. Setting it stops all spec-generator workflows from doing anything that has side effects (the workflows still run but exit early).

For a targeted rollback without disabling the entire agent fleet:

```bash
# Re-enable shadow_mode in the config.
gh variable set AGENTS_AGENTS_SPEC_GENERATOR_SHADOW_MODE --body "true"
```

This keeps classification + drafting visible in the logs (so you can keep judging quality) while side effects are suspended.

---

## Quick reference — what each workflow does

| Workflow | Trigger | Phase needed | Side effects |
|---|---|---|---|
| `spec-generator.yml` | `issues.opened/labeled` (routing label) | Phase 1+ | drafts spec, opens PR, comments issue |
| `spec-generator-iterate.yml` | `issue_comment.created` | Phase 2+ | revises spec on the spec branch, comments issue |
| `spec-generator-sweep.yml` | cron daily 09:00 UTC | Phase 2+ | applies `intent-confirmed` to silent PRs |
| `spec-generator-embed-ingest.yml` | post-merge to main | Phase 5 (deferred) | populates pgvector for dup detection |
| `spec-quality.yml` | PR opened on spec-* path | always-on | gates spec template completeness |
| `spec-required.yml` | PR opened on data-plane changes | always-on | gates `Spec:` line in PR body |
