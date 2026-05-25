Specification complete. Here's the summary:

- **`SPECIFY_FEATURE_DIRECTORY`**: `specs/004-adversarial-input-defense`
- **`SPEC_FILE`**: `specs/004-adversarial-input-defense/spec.md`
- **Short name**: `adversarial-input-defense` (derived from the adversarial-auto-approve prompt injection report)

**Checklist**: All items pass. No `[NEEDS CLARIFICATION]` markers remain.

The spec interprets the GitHub Issue #80 report as a feature request for input validation defenses against adversarial prompt injection in automated approval workflows. It covers detection, rejection, audit logging, and configuration of pattern-based defenses across all input channels, with multi-tenant isolation preserved via `saas_tenant_gate`.

Ready for `/speckit-clarify` or `/speckit-plan`.