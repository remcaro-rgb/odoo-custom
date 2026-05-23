# `club_news` — add a `website` field to the manifest

**Date:** 2026-05-23
**Author:** Tier-2 promotion smoke
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** N/A — Tier-2 first-ACT validation (SHADOW → FIXTURES)
**Severity:** low

---

## 1. Symptom

`custom-addons/club_news/__manifest__.py` declares the project-standard
metadata fields (`name`, `version`, `summary`, `category`, `author`, `license`,
`depends`, `data`, …) but is missing the optional `website` URL field. Several
peer addons include it pointing back to the source tree; `club_news` does not.

This fix-brief doubles as the **first live ACT run** of the Implementation
Agent (Tier-2 promotion from `ROLLOUT_STAGE=shadow` to `fixtures`). The agent
should drive `/speckit.implement` for real, push the resulting commit to this
PR's head branch as `implementation-bot[bot]`, and post the
"I've implemented this spec" reply.

## 2. Repro

1. `cat custom-addons/club_news/__manifest__.py`
2. There is no `'website'` key in the manifest dictionary.

**Reproduced on:** working tree at HEAD.

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only, no user-visible change.
- **Severity:** low.
- **Workaround available?** n/a — purely a hygiene fix.

## 4. Root cause

Manifest hygiene. The addon was created without the `website` field; peer
addons consistently include it.

## 5. Proposed fix

Add the `website` key to `custom-addons/club_news/__manifest__.py`, pointing
at the source tree:

```python
'website': 'https://github.com/GoliattCo/odoo-custom/tree/main/custom-addons/club_news',
```

Place it near the other top-level metadata keys (e.g. between `author` and
`license`). No other changes.

## 6. Regression test

```python
# custom-addons/club_news/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_website_is_set(self):
        with file_open('club_news/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        url = manifest.get('website', '')
        self.assertTrue(url, 'club_news manifest must declare a website URL')
        self.assertTrue(url.startswith('https://'),
                        'website URL must be https://')
```

## 7. Rollout

- Severity = low → ride the next normal wave; no hotfix flow.
- No feature flag (manifest metadata only).
- This PR is the Tier-2 **FIXTURES-stage** promotion smoke — the first time
  the Implementation Agent operates with `RolloutDecision.ACT` for this
  target. Expected outcomes:
  - workflow run logs `rollout-decision { decision: act, stage: fixtures }`
  - the agent pushes a single commit authored by `implementation-bot[bot]`
  - the workflow log includes `push.committed { sha, files: 1 }`
  - the agent posts the "implemented" PR comment as the App
