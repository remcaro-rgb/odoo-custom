-- Tier 6 spend-cap drill (2026-05-25).
--
-- Inserts a single sentinel row whose cost_usd pushes the rolling 7-day
-- sum over the $50/week cap. The agent's PostgresCostLedger should then
-- see SUM(cost_usd) = $51 and the Budget gate should refuse all new
-- drafts with skip_reason=spend_cap_reached.
--
-- Idempotent: re-runnable. The sentinel row uses issue_number = -1,
-- distinct from any real GitHub issue. CLEAN UP after verifying the
-- drill — see infra/sql/2026-05-25-spec-gen-cost-cap-cleanup.sql.

\echo === before: current weekly spend ===
SELECT
    COALESCE(SUM(cost_usd), 0)::float AS spent_week_usd
FROM spec_generator_runs
WHERE updated_at >= NOW() - INTERVAL '7 days';

\echo === insert / refresh sentinel row at $51 ===
INSERT INTO spec_generator_runs
    (issue_number, kind, confidence, branch, spec_path, cost_usd, phase, updated_at)
VALUES
    (-1, 'sentinel', 0.0, 'agent/sentinel', 'docs/sentinel.md', 51.00, 'completed', NOW())
ON CONFLICT (issue_number) DO UPDATE SET
    cost_usd = 51.00,
    updated_at = NOW();

\echo === after: new weekly spend (must exceed $50) ===
SELECT
    COALESCE(SUM(cost_usd), 0)::float AS spent_week_usd
FROM spec_generator_runs
WHERE updated_at >= NOW() - INTERVAL '7 days';

\echo === Done — sentinel row inserted. Now fire a canary issue to verify refusal. ===
