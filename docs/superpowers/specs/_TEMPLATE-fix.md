# <Title> — Fix Brief

**Date:** YYYY-MM-DD
**Author:** <name>
**Status:** Draft | In Review | Accepted
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #<NNN>
**Severity:** low | medium | high | critical

---

## 1. Symptom

What the user saw, in their own words. Include screenshots and logs (paste excerpts; full attached to PR).

> Quote the user's report verbatim if useful.

## 2. Repro

Minimal step-by-step on a fresh tenant. The reader should be able to follow these and see the bug.

1. ...
2. ...
3. ...

**Reproduced on:** agentlab snapshot YYYY-MM-DD · addons listed · browser X / OS Y.

## 3. Affected tenants & severity

- **Tenants impacted:** all / specific list (hashed IDs) / hypothetical.
- **Severity:** data loss > broken core flow > workflow degradation > UX nit.
- **Workaround available?** yes / no — if yes, summarised here.

## 4. Root cause

The actual bug, not the symptom. Cite the offending file and line.

`custom-addons/<addon>/models/<file>.py:42` — the comparison uses `==` instead of `is None`, so empty strings fall through.

If the root cause is environmental (config, infra), say so and route to a different fix path.

## 5. Proposed fix

Diff sketch. Doesn't have to be complete — just enough that a reviewer can judge approach.

```python
# before
if value == None:
    handle_empty()

# after
if value is None or value == "":
    handle_empty()
```

## 6. Regression test

The test that would have caught this bug. Mandatory — if the bug repros, a test must capture it.

```python
def test_empty_string_treated_as_none(self):
    # ...
    self.assertEqual(result, expected_handle_empty_result)
```

## 7. Rollout

- For severity ≥ high: hotfix flow (`hotfix/<slug>`) per §7.4 of the main plan.
- Otherwise: ride the next normal wave.
- Feature flag wrap? Usually no for fixes; yes if the fix changes user-visible behaviour beyond restoring documented behaviour.
