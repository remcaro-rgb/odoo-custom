# `club_news` — add a `website` field to the manifest (Tier-3 canary)

**Date:** 2026-05-23
**Author:** Tier-3 canary smoke
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** N/A — Tier-3 canary (FIXTURES → OPT_IN → DEFAULT_ON)
**Severity:** low

---

## 1. Symptom

`custom-addons/club_news/__manifest__.py` declares the project-standard
metadata fields but is missing the optional `website` URL field.

This fix-brief is the **Tier-3 canary smoke** — the first ACT run against a
clean main (the I001 lint debt was cleared in
[#31](https://github.com/GoliattCo/odoo-custom/pull/31)). The agent should
this time complete cleanly (no Gate-1 escalation), push its commit, and post
the "implemented" reply.

## 2. Repro

1. `cat custom-addons/club_news/__manifest__.py`
2. There is no `'website'` key.

**Reproduced on:** working tree at HEAD (main @ `843e66cf42`).

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a.

## 4. Root cause

Manifest hygiene. Peer addons consistently include a `website` URL pointing
back at the source; `club_news` does not.

## 5. Proposed fix

Add the `website` key to `custom-addons/club_news/__manifest__.py`:

```python
'website': 'https://github.com/GoliattCo/odoo-custom/tree/main/custom-addons/club_news',
```

Place it near the other metadata keys (between `author` and `license` works).

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
- Canary plan: this PR runs first under `ROLLOUT_STAGE=fixtures` (opt-in)
  to validate Tier-2 ACT end-to-end against a clean main, then the rollout
  promotes to `opt_in` and `default_on`. Expected outcomes:
  - `rollout-decision { decision: act, stage: fixtures }`
  - `outcome { status: implemented, shadow: false }`
  - one commit by `implementation-bot[bot]` or the container's git identity
  - an "I've implemented this spec and pushed the code" comment from the bot
  - **no `needs-human` label** (Gate-1 lint passes now)
