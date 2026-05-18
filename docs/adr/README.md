# Architecture Decision Records (ADRs)

This folder holds one-page records of architecture decisions that shaped this codebase. ADRs are **numbered, dated, and immutable once accepted** — when a decision changes, write a new ADR that supersedes the old one rather than editing.

## Format

Each ADR follows Michael Nygard's classic template:

```
# NNNN. <short decision title>

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded by NNNN | Deprecated

## Context

What forces are at play? What problem are we solving?

## Decision

What did we decide? State it actively: "We will use X."

## Consequences

What becomes easier or harder as a result?

## Alternatives considered

Brief — one paragraph per alternative and why it was rejected.
```

## Naming

`NNNN-<slug>.md` where `NNNN` is zero-padded. Increment from the highest existing number.

## Status transitions

- **Proposed** — under discussion.
- **Accepted** — decision is in force.
- **Superseded by NNNN** — a later ADR replaced this one. The old ADR stays for history.
- **Deprecated** — no longer relevant; not replaced.

## Who writes ADRs

- Any team member can propose one.
- ADRs touching infra, security, or tenancy require 2 CODEOWNERS approvals.
- ADRs touching agent charters require `security-leads` approval.
- ADRs are discussed in PRs like any other artifact.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-trunk-based-with-waves.md) | Trunk-based development with per-client waves | Accepted |
| [0002](0002-cross-platform-parity.md) | Cross-platform Railway + Fly parity | Accepted |
| [0003](0003-log-drain-better-stack.md) | Better Stack as log drain, with Loki migration path | Accepted |
