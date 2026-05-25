-- Diagnostic probe for the Tier 5 spec_gen_embeddings index.
--
-- Read-only (SELECT only). Safe to re-run. The DDL workflow runs this with
-- `psql --set=ON_ERROR_STOP=1 -f` and echoes everything to the run log,
-- so the output of these queries is visible in the GitHub Actions log.
--
-- Used live on 2026-05-25 to diagnose why the canary on issue #67 didn't
-- get a `[possible-dup]` title prefix despite a populated index.

\echo === Row counts by kind ===
SELECT kind, COUNT(*) AS rows FROM spec_gen_embeddings GROUP BY kind ORDER BY kind;

\echo === Sample issues in the index ===
SELECT kind, ref, title FROM spec_gen_embeddings WHERE kind = 'open_issue' ORDER BY ref;

\echo === Sample 5 specs in the index ===
SELECT kind, ref, title FROM spec_gen_embeddings WHERE kind = 'spec' ORDER BY ref LIMIT 5;

\echo === Nearest neighbours to issue #54 ("Add bulk-archive action to /partner list") ===
WITH q AS (
    SELECT embedding
    FROM spec_gen_embeddings
    WHERE ref = 'GoliattCo/odoo-custom#54'
    LIMIT 1
)
SELECT
    kind,
    ref,
    title,
    ROUND( (1 - (embedding <=> (SELECT embedding FROM q)))::numeric, 4) AS cosine_similarity
FROM spec_gen_embeddings
WHERE ref != 'GoliattCo/odoo-custom#54'
ORDER BY embedding <=> (SELECT embedding FROM q) ASC
LIMIT 5;

\echo === Done ===
