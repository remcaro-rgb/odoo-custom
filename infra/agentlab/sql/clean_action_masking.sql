-- One-shot remediation: reset masker output left in the Odoo
-- action-definition tables (ir_act_*) to their canonical values.
--
-- Why: ir.ui.menu.action is a Reference stored as "<model>,<id>"; at
-- `odoo -u all` Odoo builds it from the target action's `type` field. A
-- masked `type` ("MASKED:<hash>") yields "MASKED:<hash>,<id>" and the load
-- aborts with `ValueError: Wrong value for ir.ui.menu.action`. See #142.
--
-- These tables are now skipped by the masker (#142/#144), but snapshots
-- restored from a source polluted by pre-skip masking still carry the bad
-- values, and the masker cannot un-hash them — hence this deterministic
-- reset. `type` is a fixed constant per concrete action table; binding_type
-- / binding_view_types reset to Odoo-18 defaults. Only masked rows touched.
--
-- NOT covered here: per-row columns that can't be reconstructed by constant
-- (e.g. ir_actions.type, *.res_model, *.name). If discover_action_masking.sql
-- reports any of those, run `odoo -u base --stop-after-init` on the source
-- (rebuilds framework records from module XML) or re-seed from clean prod.

\set ON_ERROR_STOP on

BEGIN;

-- `type` = the action model name (constant per concrete table). THE breaker.
UPDATE ir_act_window     SET type = 'ir.actions.act_window' WHERE type LIKE 'MASKED:%' OR type LIKE '[REDACTED%';
UPDATE ir_act_client     SET type = 'ir.actions.client'     WHERE type LIKE 'MASKED:%' OR type LIKE '[REDACTED%';
UPDATE ir_act_server     SET type = 'ir.actions.server'     WHERE type LIKE 'MASKED:%' OR type LIKE '[REDACTED%';
UPDATE ir_act_report_xml SET type = 'ir.actions.report'     WHERE type LIKE 'MASKED:%' OR type LIKE '[REDACTED%';
UPDATE ir_act_url        SET type = 'ir.actions.act_url'    WHERE type LIKE 'MASKED:%' OR type LIKE '[REDACTED%';

-- binding_type (selection 'action'/'report') -> per-model default.
UPDATE ir_act_report_xml SET binding_type = 'report' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';
UPDATE ir_act_window     SET binding_type = 'action' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';
UPDATE ir_act_client     SET binding_type = 'action' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';
UPDATE ir_act_server     SET binding_type = 'action' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';
UPDATE ir_act_url        SET binding_type = 'action' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';

-- binding_view_types (Char, default 'list,form' in Odoo 18).
UPDATE ir_act_window     SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';
UPDATE ir_act_client     SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';
UPDATE ir_act_server     SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';
UPDATE ir_act_report_xml SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';
UPDATE ir_act_url        SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';

-- Base ir_actions table. `type` here holds the concrete action's model name,
-- so it varies per row and can't be a single constant. Derive it from the
-- concrete table that shares the row id (discover_action_masking.sql confirms
-- the 1:1 mapping first). This is the column the ir.ui.menu.action reference
-- is built from, so it is the actual `odoo -u all` breaker. Masked rows only.
UPDATE ir_actions a SET type = 'ir.actions.act_window' FROM ir_act_window     w WHERE w.id = a.id AND (a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%');
UPDATE ir_actions a SET type = 'ir.actions.client'     FROM ir_act_client     c WHERE c.id = a.id AND (a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%');
UPDATE ir_actions a SET type = 'ir.actions.server'     FROM ir_act_server     s WHERE s.id = a.id AND (a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%');
UPDATE ir_actions a SET type = 'ir.actions.report'     FROM ir_act_report_xml r WHERE r.id = a.id AND (a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%');
UPDATE ir_actions a SET type = 'ir.actions.act_url'    FROM ir_act_url        u WHERE u.id = a.id AND (a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%');

-- ir_actions.binding_type: 'report' for report actions, 'action' for the rest
-- (run the report join first so the catch-all doesn't clobber it).
UPDATE ir_actions a SET binding_type = 'report' FROM ir_act_report_xml r WHERE r.id = a.id AND (a.binding_type LIKE 'MASKED:%' OR a.binding_type LIKE '[REDACTED%');
UPDATE ir_actions   SET binding_type = 'action' WHERE binding_type LIKE 'MASKED:%' OR binding_type LIKE '[REDACTED%';

UPDATE ir_actions   SET binding_view_types = 'list,form' WHERE binding_view_types LIKE 'MASKED:%' OR binding_view_types LIKE '[REDACTED%';

COMMIT;
