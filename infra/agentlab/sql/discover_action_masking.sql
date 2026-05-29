-- Report every masker-polluted text column in the Odoo action-definition
-- tables. Run by .github/workflows/clean-action-masking.yml (and safe to run
-- by hand). Read-only. See issue #142.
--
-- "Polluted" = a cell holding this masker's output shape (MASKED:<hash> or
-- [REDACTED...]). These framework tables are now skipped by the masker
-- (#142/#144), but snapshots restored from a source that was masked BEFORE
-- the skip existed still carry such values — which breaks `odoo -u all`.
DO $$
DECLARE
  r record;
  n bigint;
  total bigint := 0;
BEGIN
  FOR r IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN (
        'ir_actions', 'ir_act_window', 'ir_act_window_view', 'ir_act_client',
        'ir_act_server', 'ir_act_report_xml', 'ir_act_url'
      )
      AND data_type IN ('character varying', 'text', 'character')
    ORDER BY table_name, column_name
  LOOP
    EXECUTE format(
      'SELECT count(*) FROM %I WHERE %I LIKE ''MASKED:%%'' OR %I LIKE ''[REDACTED%%''',
      r.table_name, r.column_name, r.column_name
    ) INTO n;
    IF n > 0 THEN
      RAISE NOTICE 'polluted: %.% = % row(s)', r.table_name, r.column_name, n;
      total := total + n;
    END IF;
  END LOOP;
  RAISE NOTICE 'total polluted action-table cells: %', total;
  IF total = 0 THEN
    RAISE NOTICE 'clean: no masker output in the action-definition tables';
  END IF;
END $$;

-- ir_actions id-mapping integrity. The base table's `type` can't be reset to
-- a single constant (it varies per row), so clean_action_masking.sql derives
-- it by joining each masked base row to the concrete table sharing its id.
-- That is only correct if every masked base row maps to EXACTLY ONE concrete
-- table. This reports the breakdown so the reconstruction can be trusted
-- (safe to apply iff unmapped=0 AND multi=0 AND unique=masked).
DO $$
DECLARE masked bigint; uniq bigint; unmapped bigint; multi bigint;
BEGIN
  SELECT count(*),
         count(*) FILTER (WHERE nmatch = 1),
         count(*) FILTER (WHERE nmatch = 0),
         count(*) FILTER (WHERE nmatch > 1)
    INTO masked, uniq, unmapped, multi
  FROM (
    SELECT (a.id IN (SELECT id FROM ir_act_window))::int
         + (a.id IN (SELECT id FROM ir_act_client))::int
         + (a.id IN (SELECT id FROM ir_act_server))::int
         + (a.id IN (SELECT id FROM ir_act_report_xml))::int
         + (a.id IN (SELECT id FROM ir_act_url))::int AS nmatch
    FROM ir_actions a
    WHERE a.type LIKE 'MASKED:%' OR a.type LIKE '[REDACTED%'
  ) t;
  RAISE NOTICE 'ir_actions type-mask id-mapping: masked=% unique=% unmapped=% multi=%',
    masked, uniq, unmapped, multi;
END $$;
