# `club_events` — add a `maintainers` field to the manifest

**Date:** 2026-05-23
**Author:** Tier-7 live validation (snapshot armed via `/project/git/init`)
**Status:** In Review
**Spec type:** fix-brief
**Linked issue:** N/A — Tier-7 end-to-end validation of the get_diff fix
**Severity:** low

---

## 1. Symptom

`custom-addons/club_events/__manifest__.py` declares the project-standard
metadata fields but is missing the optional `maintainers` field. Same shape
as PR #35 (`club_faq`), exercised against `club_events` so the two PRs land
through visibly different push paths — PR #35 by the container as
"Implementation Agent <impl-agent@goliatt.co>" (the Tier-6 workaround), and
this one by the GitHub App as `implementation-bot[bot]` (the Tier-7
clean path now that OpenCode's shadow-git snapshots are armed).

## 2. Repro

1. `cat custom-addons/club_events/__manifest__.py`
2. There is no `'maintainers'` key in the manifest dictionary.

**Reproduced on:** working tree at HEAD of main.

## 3. Affected tenants & severity

- **Tenants impacted:** none — manifest metadata only.
- **Severity:** low.
- **Workaround:** n/a — hygiene fix.

## 4. Root cause

Manifest hygiene. `club_events` predates the maintainers convention; adding
it brings the manifest into line with the project's metadata conventions
and matches what PR #35 just landed on `club_faq`.

## 5. Proposed fix

Add the `maintainers` key to `custom-addons/club_events/__manifest__.py`
as a single-element list of the author:

```python
'maintainers': ['Manuel Caro'],
```

Place it near the other metadata keys (between `author` and `license`
works). No other changes.

## 6. Regression test

```python
# custom-addons/club_events/tests/test_manifest.py
import ast
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestManifest(TransactionCase):
    def test_maintainers_is_a_non_empty_list(self):
        with file_open('club_events/__manifest__.py', 'r') as fh:
            manifest = ast.literal_eval(fh.read())
        maintainers = manifest.get('maintainers')
        self.assertIsInstance(maintainers, list)
        self.assertTrue(maintainers, 'maintainers list must not be empty')
```

## 7. Rollout

- Severity = low → ride the next normal wave.
- No feature flag.
- Expected outcomes (rollout `ROLLOUT_STAGE=default_on`, post Tier-7):
  - `rollout-decision { decision: act, stage: default_on }`
  - `/speckit.fix` is the command issued.
  - **One commit on the PR head branch, authored by
    `implementation-bot[bot]`** — NOT by `Implementation Agent
    <impl-agent@goliatt.co>` (that was the Tier-6 workaround the
    deployed `speckit.fix.md` no longer instructs).
  - `outcome { status: implemented }` + a comment from the bot.
  - **No `needs-human` label.**
