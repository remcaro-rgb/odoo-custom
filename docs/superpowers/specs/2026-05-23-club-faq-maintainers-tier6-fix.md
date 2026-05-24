# `club_faq` — add a `maintainers` field to the manifest

**Date:** 2026-05-23
**Author:** Tier-6 live re-test (`/speckit.fix` routing)
**Status:** In Review
**Spec type:** fix-brief
**Linked issue:** N/A — direct A/B test against the no-op `/speckit.implement` runs on closed PR #34
**Severity:** low

---

## 1. Symptom

`custom-addons/club_faq/__manifest__.py` declares the project-standard
metadata fields but is missing the optional `maintainers` field. This is
the same spec as PR #34 (closed) — on PR #34 the agent ran twice via
`/speckit.implement` and produced no diff both times because the
fast-path has no `tasks.md` to read. This PR re-tries the same task
through the project-owned `/speckit.fix` command (Tier 6).

## 2. Repro

1. `cat custom-addons/club_faq/__manifest__.py`
2. There is no `'maintainers'` key in the manifest dictionary.

**Reproduced on:** working tree at HEAD.

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a — hygiene fix.

## 4. Root cause

Manifest hygiene. `club_faq` predates the maintainers convention; adding
it brings the manifest into line with the project's metadata conventions.

## 5. Proposed fix

Add the `maintainers` key to `custom-addons/club_faq/__manifest__.py` as
a single-element list of the author:

```python
'maintainers': ['Manuel Caro'],
```

Place it near the other metadata keys (between `author` and `license`
works). No other changes.

## 6. Regression test

```python
# custom-addons/club_faq/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_maintainers_is_a_non_empty_list(self):
        with file_open('club_faq/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
```

## 7. Rollout

- Severity = low → ride the next normal wave.
- No feature flag.
- Expected outcomes (rollout `ROLLOUT_STAGE=default_on`):
  - `rollout-decision { decision: act, stage: default_on }`
  - `/speckit.fix` is the command issued (NOT `/speckit.implement`).
  - One commit by the agent on the PR head branch with the `maintainers`
    field added.
  - `outcome { status: implemented }` + a comment from the bot.
  - **No `needs-human` label.**
