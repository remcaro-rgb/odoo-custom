#!/bin/bash
# mask-prod-data.sh — apply masking to a fresh agentlab restore.
#
# Reads:
#   - mask-allowlist.yml  (columns explicitly safe to leave unmasked)
#   - masking-rules.yml   (per-type strategy + universal deny-list patterns)
#
# Pipeline:
#   1. Connect to the just-restored agentlab Postgres
#   2. For every table.column NOT in the allow-list:
#        - look up column type
#        - apply the strategy from masking-rules.yml
#   3. Run the universal deny-list regex pass over any text columns
#      that don't already have a more specific strategy
#   4. Sample 100 random rows across the DB; assert no PII patterns leak
#   5. Emit metrics to stdout (structured JSON)
#
# Audit: every run writes a row to saas.audit.event via the control plane.
#
# Skeleton implementation — replace TODOs before first prod use.

set -euo pipefail

AGENTLAB_DSN="${AGENTLAB_DSN:?AGENTLAB_DSN env var required}"
ALLOWLIST="${ALLOWLIST:-$(dirname "$0")/mask-allowlist.yml}"
RULES="${RULES:-$(dirname "$0")/masking-rules.yml}"
SAMPLE_SIZE="${SAMPLE_SIZE:-100}"
LOG=$(mktemp)
trap "rm -f $LOG" EXIT

log() {
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf '{"ts":"%s","level":"%s","msg":"%s"}\n' "$ts" "$1" "$2"
}

log info "mask-prod-data.start dsn=$AGENTLAB_DSN allowlist=$ALLOWLIST"

# 1. Validate config files exist
[ -f "$ALLOWLIST" ] || { log error "mask-allowlist not found at $ALLOWLIST"; exit 1; }
[ -f "$RULES" ]     || { log error "masking-rules not found at $RULES"; exit 1; }

# 2. Enumerate target databases (every DB in the cluster except postgres+template)
DBS=$(psql "$AGENTLAB_DSN" -t -A -c \
    "SELECT datname FROM pg_database WHERE datname NOT IN ('postgres','template0','template1');")

for db in $DBS; do
    log info "mask.database.start db=$db"
    DB_DSN="${AGENTLAB_DSN%/*}/$db"

    # 3. Apply column-type-based masking
    #
    # TODO: implement the actual masking. Sketch:
    #
    # python - <<EOF
    # import yaml, psycopg
    # allow = yaml.safe_load(open("$ALLOWLIST"))['allowed']
    # rules = yaml.safe_load(open("$RULES"))
    # with psycopg.connect("$DB_DSN") as conn, conn.cursor() as cur:
    #     cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public';")
    #     for table, column, dtype in cur.fetchall():
    #         if column in allow.get(table, []):
    #             continue
    #         strategy = pick_strategy(dtype, column, rules)
    #         apply_strategy(cur, table, column, strategy)
    # EOF
    log info "mask.database.todo db=$db msg='masking implementation pending'"

    # 4. Universal deny-list regex pass on text columns
    log info "mask.database.deny_list.todo db=$db msg='regex pass implementation pending'"

    # 5. Sample audit
    log info "mask.database.audit.todo db=$db sample_size=$SAMPLE_SIZE"

    log info "mask.database.end db=$db"
done

log info "mask-prod-data.end"

# 6. Write audit event (TODO: psql against control-plane DSN)
# psql "$CONTROL_PLANE_DSN" -c "
#   INSERT INTO saas.audit.event (actor_kind, actor_name, action, payload)
#   VALUES ('system', 'mask-prod-data', 'masking-applied',
#           jsonb_build_object('dbs', '$DBS', 'sample_size', $SAMPLE_SIZE))
# "

echo "WARNING: this script is a skeleton. See docs/superpowers/specs/2026-05-16-agentlab-environment-design.md §5 for the full pipeline." >&2
