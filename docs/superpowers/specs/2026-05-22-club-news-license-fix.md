# `club_news` — License declaration fix

**Date:** 2026-05-22
**Author:** Tier-1 deployment smoke
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** N/A — Tier-1 Implementation Agent deployment smoke.
**Severity:** low

---

## 1. Symptom

The `club_news` addon's `__manifest__.py` is being audited for compliance with
the project's manifest convention (per `opencode/AGENTS.md`: every addon must
declare `license`).

This fix-brief doubles as the **first live SHADOW-mode run of the Implementation
Agent** (`docs/2026-05-20-implementation-agent-alt-design.md` + the Tier-1
runbook in `remcaro-rgb/Odoo-saas-agents`). With `ROLLOUT_STAGE=shadow` the
agent drives OpenCode for real but posts no comment or label — its outcome is
visible only in the Action's structured JSON log records.

## 2. Repro

1. Open `custom-addons/club_news/__manifest__.py`.
2. Confirm the `license` field is exactly `'LGPL-3'` (the project standard).
3. If missing or different, that's the bug.

**Reproduced on:** working tree at HEAD (`main`).

## 3. Affected tenants & severity

- **Tenants impacted:** none — this is code-hygiene, no behaviour change.
- **Severity:** low.
- **Workaround available?** n/a — the addon installs either way; this is a
  consistency/audit fix.

## 4. Root cause

Manifest hygiene: addons that omit (or mis-declare) `license` fail the
`AGENTS.md` "always declare … license" rule and confuse downstream consumers.
The fix is a one-line manifest update.

## 5. Proposed fix

```python
# in custom-addons/club_news/__manifest__.py — ensure this key is present and
# set to the project standard:
'license': 'LGPL-3',
```

No other changes. If the field is already correct, no edit is required — the
agent should detect that and post (drafted, in shadow) a "no changes needed"
note.

## 6. Regression test

```python
# custom-addons/club_news/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_license_is_lgpl3(self):
        with file_open('club_news/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        self.assertEqual(
            manifest.get('license'), 'LGPL-3',
            'club_news manifest must declare LGPL-3 (AGENTS.md convention)',
        )
```

## 7. Rollout

- Severity = low → ride the next normal wave; no hotfix flow.
- No feature flag (no behaviour change).
- This PR exists primarily to validate the Implementation Agent's runnable
  layer end-to-end. After the shadow run completes and the Action log shows
  the expected JSON records (`rollout-decision`, `outcome`), the PR can be
  closed or merged regardless of the agent's draft outcome.
