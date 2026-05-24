# `account_product_category_accounts` — add `maintainers` + `author` to manifest

**Date:** 2026-05-24
**Author:** Tier-7 post-merge live validation (Bug 1 + Bug 2 fixes)
**Status:** In Review
**Spec type:** fix-brief
**Linked issue:** N/A — validates commits `4b80156` (auto-isort + phantom-skip)
**Severity:** low

---

## 1. Symptom

`custom-addons/account_product_category_accounts/__manifest__.py` is
missing the `author` and `maintainers` metadata fields.

## 2. Repro

1. `cat custom-addons/account_product_category_accounts/__manifest__.py`
2. Neither key is present.

**Reproduced on:** working tree at HEAD of main.

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a — hygiene fix.

## 4. Root cause

Manifest hygiene. `account_product_category_accounts` predates the
metadata convention; adding the fields brings it in line.

## 5. Proposed fix

Add the two keys to
`custom-addons/account_product_category_accounts/__manifest__.py`:

```python
'author': 'Manuel Caro',
'maintainers': ['Manuel Caro'],
```

Place them between `summary` and `category`. No other changes.

## 6. Regression test

```python
# custom-addons/account_product_category_accounts/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_author_and_maintainers_are_set(self):
        with file_open(
            'account_product_category_accounts/__manifest__.py', 'r'
        ) as fh:
            manifest = ast.literal_eval(fh.read())
        assert manifest.get('author'), 'author must be set'
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
```

## 7. Rollout

- Severity = low → ride the next normal wave.
- Expected outcomes (validation of commits `4b80156` + the full Tier-7 chain):
  - Bot commit lands authored by `implementation-bot[bot]`.
  - Gate-1 `lint` PASSES on the first iteration — `auto_isort` resolves
    the I001 the agent would otherwise introduce on `tests/__init__.py`.
  - **EXACTLY ONE** "implemented this spec and pushed the code" bot
    comment, posted AFTER the bot's commit timestamp.
  - `outcome { status: implemented }` in the run log.
  - No `needs-human` label.
