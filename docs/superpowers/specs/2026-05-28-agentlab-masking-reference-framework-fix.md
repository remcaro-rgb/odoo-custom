# Agentlab masking — passthrough reference fields + UI/action framework tables

**Date:** 2026-05-28
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #142
**Severity:** high

---

## 1. Symptom

After #141 fixed the first layer of masking corruption (`ir_model_data`), a
fresh re-mask + `migration-dry-run-staging` got far further into `odoo -u all`
and then failed at a second layer:

```
ValueError: Wrong value for ir.ui.menu.action: 'MASKED:d04ef9d99cd0,5'
while parsing /odoo/odoo/addons/base/views/decimal_precision_views.xml:36
<menuitem ... action="action_decimal_precision_form"/>
```

## 2. Repro

1. Re-mask agentlab with the post-#141 masker (`agentlab-daily-restore -f dry_run=false`).
2. Run `migration-dry-run-staging` against a freshly-masked tenant.
3. `Run odoo -u all` aborts on the masked `ir.ui.menu.action` reference value.

**Reproduced on:** dry-run `26586152181` (tenant `acmesas2`, freshly re-masked;
`structural_skipped_columns: 129` confirmed the #141 skip ran).

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (agentlab/CI).
- **Severity:** high — masked snapshots remain unloadable by `-u all`, so the
  migration safety net stays offline on real data.

## 4. Root cause

The masker masks every non-allowlisted column. Two gaps remained after #141:

1. **`reference` fields** (ttype `reference`, stored as `"model,id"`) were
   routed to a text strategy and hashed, so the pointer no longer parses.
   `ir.ui.menu.action` is the first to bite, but the bug is generic to every
   reference field. A reference is a polymorphic FK — it never carries PII.
2. **UI / action-definition tables** (`ir_ui_menu`, `ir_ui_view`,
   `ir_actions_*`) are framework definitions that `-u all` rewrites from each
   module's XML; masking their columns corrupts that load. They are not in
   `_STRUCTURAL_TABLES`.

This is the pattern documented in #142: deny-all-but-allowlist masking
corrupts framework data, and `-u all` surfaces it one layer at a time.

## 5. Proposed fix (the approved #142 strategy, code parts)

`infra/agentlab/mask_prod_data.py`:

1. **Treat ttype `reference` as passthrough** in `classify_column` (route to
   `foreign_key`, same as `many2one`/`one2many`/`many2many`). One change
   protects every reference field. Also added to `_PASSTHROUGH_TTYPES`.
2. **Add UI/action framework-definition tables to `_STRUCTURAL_TABLES`**:
   `ir_ui_menu`, `ir_ui_view`, `ir_ui_view_custom`, `ir_actions_actions`,
   `ir_act_window`, `ir_act_window_view`, `ir_act_url`, `ir_act_server`,
   `ir_act_report_xml`, `ir_act_client`.

Both are belt-and-suspenders for `ir.ui.menu.action` (covered by reference
passthrough AND the table skip). Still an **explicit list, not a blanket
`ir_*` skip** — PII/secret-bearing `ir_` tables (`ir_attachment`,
`ir_mail_server`, `ir_config_parameter`, `ir_logging`) keep being masked.

### Security posture (why this is safe)

This keeps deny-by-default for all tenant/business data (fail-loud); it only
exempts framework/structural definitions and typed pointers, which are
code-defined and identical across tenants. It does **not** invert to
allow-by-default (which would leak PII through omission). See the strategy
evaluation in #142.

## 6. Regression test

`infra/agentlab/tests/test_masking.py` (127 passing):
- `reference` ttype → `foreign_key` for varchar/text/character; its
  `strategy_sql` is `None` (passthrough).
- `is_structural_table()` True for the added UI/action tables; still False for
  `ir_attachment`/`ir_mail_server`/`ir_config_parameter`/`ir_logging` and
  tenant tables (guards against over-exemption).
- `ir.ui.menu.action` doubly protected (table skip + reference passthrough).

## 7. Rollout

- Severity = high → fix now (this PR).
- **Security-governed** (touches the masking trust boundary) — strategy
  approved on #142; this is the code implementation of options 1+2.
- **Companion follow-up (option 3, NOT in this PR):** add a post-mask
  `odoo -u …--stop-after-init` smoke to `agentlab-daily-restore` so a masked
  snapshot that won't load fails the restore. It's a heavier workflow change
  that overlaps #143's masking-step hardening (exit-code handling), and can't
  be verified from the automation sandbox — recommended to land with #143.
- **Verification:** unit tests in CI ("Agentlab masking unit tests"); the
  end-to-end proof is a re-mask + `migration-dry-run-staging` (will reveal any
  layer 3, per #142).
