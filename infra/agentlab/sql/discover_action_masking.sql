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
