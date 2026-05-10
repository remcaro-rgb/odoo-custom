# Vacuum freeze — transaction-ID wraparound

Stub. Steps:

1. Check `SELECT datname, age(datfrozenxid) FROM pg_database ORDER BY 2 DESC;` —
   any DB whose age exceeds `autovacuum_freeze_max_age` (default 200M) is at
   risk.
2. Manual `VACUUM (FREEZE, VERBOSE) <table>;` against the largest offenders
   in the at-risk DBs.
3. If autovacuum is keeping up but slowly, raise `autovacuum_max_workers` in
   `postgresql.conf` and reload (`SELECT pg_reload_conf();`).
4. If urgent (age > 1.5B): plan a single-user vacuum window — Odoo must be
   stopped against that DB for the duration.
