# Agent Charters

Every AI agent in this repo has a **charter** here. The charter is the
agent's contract with the rest of the system: what it's allowed to do, what
it must not do, what triggers it, and what stops it.

Charters are **human-edited only**. Agents themselves CANNOT modify charters
(enforced by the `agent-guardrails` CI workflow + CODEOWNERS).

## Format

Each charter follows the same shape:

```
# <agent-name> Charter

**Status:** Active | Paused
**Owner:** <team>
**Spec:** <path to design spec>

## 1. Identity
## 2. Trigger
## 3. Allowed scope
## 4. Forbidden
## 5. Caps
## 6. Loops (or sequences)
## 7. Escalation paths
## 8. Kill switch
```

## Index

| Agent | Bucket | Charter |
|---|---|---|
| Spec Generator | engineering | [spec-generator.md](spec-generator.md) |
| Implementation | engineering | [implementation.md](implementation.md) |
| Code | engineering | [code.md](code.md) |
| Security | engineering | [security.md](security.md) |
| Optimization | engineering | [optimization.md](optimization.md) |
| Support Triage | customer-facing | [support-triage.md](support-triage.md) |
