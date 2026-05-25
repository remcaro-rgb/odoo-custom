-- Tier 6 spend-cap drill cleanup.
--
-- Removes the sentinel row inserted by 2026-05-25-spec-gen-cost-cap-drill.sql.
-- Run AFTER the drill confirms the cap fires, so production goes back
-- to its real spend level (~$0 right now).

\echo === before: current weekly spend ===
SELECT
    COALESCE(SUM(cost_usd), 0)::float AS spent_week_usd
FROM spec_generator_runs
WHERE updated_at >= NOW() - INTERVAL '7 days';

\echo === delete sentinel row ===
DELETE FROM spec_generator_runs WHERE issue_number = -1;

\echo === after: spend back to baseline ===
SELECT
    COALESCE(SUM(cost_usd), 0)::float AS spent_week_usd
FROM spec_generator_runs
WHERE updated_at >= NOW() - INTERVAL '7 days';

\echo === Done — sentinel cleaned up. ===
