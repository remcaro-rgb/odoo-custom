# `club_faq` — add a `maintainers` field to the manifest

**Date:** 2026-05-23
**Author:** Pattern-repeat smoke (Tier-5 confirmation, different addon + field)
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** N/A — Implementation Agent pattern-repeat validation
**Severity:** low

---

## 1. Symptom

`custom-addons/club_faq/__manifest__.py` declares the project-standard
metadata fields but is missing the optional `maintainers` field. This blocks a
small piece of addon-ownership clarity (and is the project convention for
addons that have a known author / maintainer).

This fix-brief is a **different-addon, different-field-type** smoke confirming
the Implementation Agent's productive ACT pattern repeats from PR #32:

- Different addon (`club_faq` vs the previous `club_news`).
- Different field type (`maintainers` is a **list of strings** vs `website`'s
  bare string).
- Clean Gate-1 baseline (lint debt cleared in
  [#33](https://github.com/GoliattCo/odoo-custom/pull/33)).

## 2. Repro

1. `cat custom-addons/club_faq/__manifest__.py`
2. There is no `'maintainers'` key in the manifest dictionary.

**Reproduced on:** working tree at HEAD (main @ `fa15991566`).

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a — hygiene fix.

## 4. Root cause

Manifest hygiene. `club_faq` predates the maintainers convention; adding it
brings the manifest into line with the project's metadata conventions.

## 5. Proposed fix

Add the `maintainers` key to `custom-addons/club_faq/__manifest__.py` as a
single-element list of the author:

```python
'maintainers': ['Manuel Caro'],
```

Place it near the other metadata keys (between `author` and `license` works).
No other changes.

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

- Severity = low → ride the next normal wave; no hotfix flow.
- No feature flag (manifest metadata only).
- Expected outcomes (rollout currently `ROLLOUT_STAGE=default_on`):
  - `rollout-decision { decision: act, stage: default_on }`
  - `outcome { status: implemented, shadow: false }`
  - one commit by the bot (`Implementation Agent` via the container's
    autonomous git, or `implementation-bot[bot]` via the Action runner)
  - an "I've implemented this spec" comment from `implementation-bot-goliattco`
  - **no `needs-human` label**
