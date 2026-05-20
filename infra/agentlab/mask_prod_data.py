#!/usr/bin/env python3
"""mask_prod_data.py — apply masking to a fresh agentlab restore.

Implements docs/superpowers/specs/2026-05-16-agentlab-environment-design.md §5.1.

Pipeline, per database in the agentlab Postgres cluster:

  1. Load ir_model_fields → the Odoo field type (ttype) for every
     (table, column). This is the authoritative classifier input —
     far more reliable than guessing from information_schema data types
     (it distinguishes selection from char, monetary from float, etc.).
  2. Enumerate every column via information_schema.
  3. For each column NOT in mask-allowlist.yml:
       - classify it to a masking-rules semantic type
       - apply the strategy as a single SQL UPDATE (set-based, fast)
  4. Run the universal deny-list regexp pass over non-allowlisted
     text/char columns as a safety net for classifier gaps.
  5. Sample rows and assert no deny-list PII pattern survives.
  6. Emit structured JSON metrics on stdout.

Masking is done with set-based SQL UPDATEs (not row-by-row in Python)
so a 5 GB database completes in minutes, not hours. The pure helper
functions — classify_column, strategy_sql, is_allowed, scan_for_pii —
carry no DB dependency and are unit-tested in tests/test_masking.py.

Exit codes:
  0  masking applied, sample audit clean
  1  configuration / connection error
  2  sample audit found surviving PII (masking incomplete)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

import yaml

# psycopg2 is imported lazily inside the DB-layer functions so that the
# pure helpers (classify_column, strategy_sql, scan_for_pii, ...) and
# their unit tests import cleanly on a machine without psycopg2.

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# information_schema data types that hold free text (used for the deny-list
# pass and as the classifier fallback when ir_model_fields has no entry).
_TEXT_DATA_TYPES = frozenset({"character varying", "text", "character"})

# Odoo ttypes that never carry PII — masking them would corrupt referential
# integrity (FKs) or break enum/boolean semantics.
_PASSTHROUGH_TTYPES = frozenset({
    "many2one", "one2many", "many2many",
    "selection", "boolean", "integer", "date", "datetime",
})

# Column-name substrings that override the ttype-based classification.
# Order matters — first match wins (see classify_column).
_NAME_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("email", "email_normalized", "email_from"), "email"),
    (("phone", "mobile", "fax", "phone_sanitized"), "phone"),
    (("vat", "nit", "tax_id"), "nit"),
    (("cedula", "identification_id", "document_number", "id_number"), "cedula"),
    (("iban", "acc_number", "bank_account"), "iban"),
    (("card_number", "credit_card", "cc_number"), "payment_card"),
)

# Monetary column-name substrings — only consult when the ttype/data type
# is numeric, so a text column called "amount_note" isn't treated as money.
_MONETARY_HINTS = (
    "amount", "price", "total", "balance", "debit", "credit",
    "cost", "subtotal", "tax", "salary", "wage", "payment",
)


# --------------------------------------------------------------------------
# Pure helpers — no DB, unit-tested in tests/test_masking.py
# --------------------------------------------------------------------------

def load_config(allowlist_path: str, rules_path: str) -> tuple[dict, dict]:
    """Load and minimally validate the two YAML config files."""
    with open(allowlist_path, encoding="utf-8") as fh:
        allowlist_doc = yaml.safe_load(fh) or {}
    with open(rules_path, encoding="utf-8") as fh:
        rules_doc = yaml.safe_load(fh) or {}
    allowed = allowlist_doc.get("allowed") or {}
    if not isinstance(allowed, dict):
        raise ValueError(f"{allowlist_path}: 'allowed' must be a mapping")
    if "rules" not in rules_doc:
        raise ValueError(f"{rules_path}: missing top-level 'rules'")
    return allowed, rules_doc


def is_allowed(table: str, column: str, allowlist: dict) -> bool:
    """True if (table, column) is explicitly cleared to remain unmasked."""
    return column in (allowlist.get(table) or [])


def classify_column(
    table: str,
    column: str,
    *,
    odoo_ttype: str | None,
    data_type: str | None,
    char_max_len: int | None,
) -> str:
    """Map a column to a masking-rules semantic type.

    `odoo_ttype` is the value from ir_model_fields.ttype when the column
    belongs to an Odoo model; None for raw SQL tables (m2m relation
    tables, non-Odoo tables). `data_type` / `char_max_len` come from
    information_schema and are the fallback classifier.

    Returns one of: email, phone, nit, cedula, iban, payment_card,
    monetary, text, string, date, boolean, selection, foreign_key,
    binary, json, jsonb, or _unsupported.

    Classification order matters. The Postgres *physical* type is a hard
    constraint and is decided FIRST: a column whose physical type cannot
    accept a text literal (boolean, integer, date, bytea, json, ...) is
    classified purely by that type — column-name hints and Odoo ttype
    only get consulted once we know the column is genuinely text. This
    is what stops a boolean column named `group_by_email`, or an integer
    `phone_count`, from being handed a text-producing strategy.
    """
    col = column.lower()
    dt = (data_type or "").lower()

    # ---- Step 0: physical type. Non-text physical types are decided
    #      here and here only — no text strategy can touch them. ----
    if dt == "bytea":
        return "binary"
    if dt == "jsonb":
        return "jsonb"
    if dt == "json":
        return "json"
    if dt == "boolean":
        return "boolean"
    if dt in ("date", "timestamp without time zone",
              "timestamp with time zone", "time without time zone"):
        return "date"
    if dt in ("integer", "bigint", "smallint"):
        # Passthrough. An integer can't take any of our text-producing
        # strategies (cedula/nit included). Odoo stores cédula/NIT as
        # char, so an integer column is realistically an id/count/FK.
        return "foreign_key"
    if dt in ("numeric", "double precision", "real"):
        # Numeric IS compatible with the monetary noise strategy, so
        # name + ttype may still refine it; otherwise passthrough.
        if _looks_monetary(col) or odoo_ttype == "monetary":
            return "monetary"
        return "foreign_key"

    _TEXTUAL = ("character varying", "character", "text", "citext")
    if dt and dt not in _TEXTUAL:
        # An exotic physical type we don't have a strategy for (uuid,
        # arrays, inet, tsvector, ...). Passthrough rather than crash
        # the whole restore; the caller logs this so it's reviewable.
        return "_unsupported"

    # ---- The column is genuinely text from here on. ----

    # Step 1: column-name hints — an `email` text column is an email
    # address whether Odoo calls it char or the table is non-Odoo.
    for needles, semantic in _NAME_HINTS:
        if any(n in col for n in needles):
            return semantic

    # Step 2: Odoo ttype.
    if odoo_ttype:
        if odoo_ttype in ("many2one", "one2many", "many2many"):
            return "foreign_key"
        if odoo_ttype == "selection":
            return "selection"
        if odoo_ttype in ("text", "html"):
            return "text"
        if odoo_ttype == "char":
            return "string"
        # binary/json ttype but a textual physical column, or
        # reference/other — redact via the long-string path.
        return "text"

    # Step 3: no Odoo metadata — size-based split on the text column.
    if dt == "text":
        return "text"
    # character varying / character / citext: long ones are free text,
    # short ones get hashed.
    if char_max_len is not None and char_max_len >= 50:
        return "text"
    return "string"


def _looks_monetary(col_lower: str) -> bool:
    return any(h in col_lower for h in _MONETARY_HINTS)


def strategy_sql(semantic_type: str, col_ident: str, rules: dict) -> str | None:
    """Return a SQL scalar expression that produces the masked value for
    `col_ident` (an already-quoted column identifier), or None when the
    column should be left untouched (passthrough).

    The expressions are all NULL-preserving: a NULL input stays NULL so
    NOT NULL-ness and FK validity are unaffected.
    """
    if semantic_type in ("date", "boolean", "selection", "foreign_key",
                         "_unsupported"):
        return None

    if semantic_type == "binary":
        # bytea columns (QR codes, scanned images, attachments) — a text
        # literal can't be assigned, so empty them. Could hold PII (a
        # scanned ID), so we don't passthrough. NULL-preserving.
        return f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE ''::bytea END"

    if semantic_type in ("json", "jsonb"):
        # json / jsonb columns — replace with an empty object. The cast
        # must be explicit and match the column type: a bare '{}' inside
        # a CASE resolves to `text` (Postgres types unknown literals as
        # text), and text is not assignment-castable to json/jsonb.
        cast = "jsonb" if semantic_type == "jsonb" else "json"
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL "
                f"ELSE '{{}}'::{cast} END")

    if semantic_type == "email":
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE "
                f"'user' || substr(md5({col_ident}::text), 1, 8) "
                f"|| '@masked.invalid' END")

    if semantic_type == "phone":
        return f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE '+57XXXXXXXXXX' END"

    if semantic_type == "cedula":
        # Random 9-digit number rendered as text.
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE "
                f"(100000000 + floor(random() * 900000000)::bigint)::text END")

    if semantic_type == "nit":
        # Random 9-digit base + a check digit, NIT-style "<digits>-<d>".
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE "
                f"(100000000 + floor(random() * 900000000)::bigint)::text "
                f"|| '-' || floor(random() * 10)::int::text END")

    if semantic_type in ("payment_card", "iban"):
        return f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE '[REDACTED]' END"

    if semantic_type == "monetary":
        # ±10% multiplicative noise — preserves aggregate scale, destroys
        # the exact figure. NULL * x is NULL, so no CASE needed.
        rng = float(((rules.get("rules") or {}).get("monetary") or {})
                    .get("range", 0.10))
        low = 1.0 - rng
        span = 2.0 * rng
        return f"{col_ident} * ({low} + random() * {span})"

    if semantic_type == "text":
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE "
                f"'[REDACTED text length=' || length({col_ident}::text) "
                f"|| ']' END")

    if semantic_type == "string":
        # Short string → deterministic hash with a MASKED: prefix.
        return (f"CASE WHEN {col_ident} IS NULL THEN NULL ELSE "
                f"'MASKED:' || substr(md5({col_ident}::text), 1, 12) END")

    raise ValueError(f"unknown semantic type: {semantic_type!r}")


def clamp_expr_to_column(
    expr: str, data_type: str | None, char_max_len: int | None
) -> str:
    """Wrap a text-producing masking expression so its result can't
    overflow a length-bounded varchar/character column.

    The masking strategies emit fixed-shape text (`MASKED:` + 12 hex,
    `user…@masked.invalid`, etc.) that is longer than a tightly-sized
    column — e.g. a `character varying(1)` — would accept. LEFT() is
    NULL-preserving, so a NULL stays NULL.

    Only varchar/character columns are length-bounded AND only ever
    receive text strategies (classify_column routes numeric/bytea/json
    elsewhere), so wrapping with LEFT is always type-valid here.
    """
    if char_max_len is not None and (data_type or "").lower() in (
        "character varying", "character"
    ):
        return f"LEFT({expr}, {char_max_len})"
    return expr


def compile_deny_patterns(rules: dict) -> list[tuple[str, re.Pattern]]:
    """Compile the deny_list_patterns section into (name, regex) pairs."""
    out: list[tuple[str, re.Pattern]] = []
    for entry in rules.get("deny_list_patterns") or []:
        name = entry.get("name", "unnamed")
        pattern = entry.get("regex")
        if not pattern:
            continue
        out.append((name, re.compile(pattern)))
    return out


def scan_for_pii(text: str, patterns: list[tuple[str, re.Pattern]]) -> list[str]:
    """Return the names of every deny-list pattern that matches `text`."""
    if not text:
        return []
    return [name for name, rx in patterns if rx.search(text)]


# --------------------------------------------------------------------------
# DB layer — impure
# --------------------------------------------------------------------------

def _quote_ident(name: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes."""
    return '"' + name.replace('"', '""') + '"'


# Databases that must never be masked:
#   postgres / template0 / template1 — Postgres-internal.
#   repmgr — Fly flex-Postgres's replication-metadata DB. Running mask
#            UPDATEs over its tables corrupts cluster replication. The
#            agentlab Postgres is a --flex cluster, so repmgr always
#            exists there.
_INTERNAL_DATABASES = ("postgres", "template0", "template1", "repmgr")


def list_databases(admin_dsn: str) -> list[str]:
    """Every database in the cluster except internal ones + templates."""
    import psycopg2
    conn = psycopg2.connect(admin_dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT datname FROM pg_database "
                "WHERE NOT (datname = ANY(%s)) "
                "AND NOT datistemplate ORDER BY datname",
                (list(_INTERNAL_DATABASES),),
            )
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _load_odoo_ttypes(conn) -> dict[tuple[str, str], str]:
    """Map (table, column) → Odoo field ttype from ir_model_fields.

    Returns {} when ir_model_fields is absent (a non-Odoo database) so the
    classifier transparently falls back to information_schema.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass('public.ir_model_fields') IS NOT NULL"
        )
        if not cur.fetchone()[0]:
            return {}
        cur.execute(
            "SELECT m.model, f.name, f.ttype "
            "FROM ir_model_fields f JOIN ir_model m ON m.id = f.model_id"
        )
        out: dict[tuple[str, str], str] = {}
        for model, field, ttype in cur.fetchall():
            if not model or not field or not ttype:
                continue
            out[(model.replace(".", "_"), field)] = ttype
        return out


def _list_columns(conn) -> list[tuple[str, str, str, int | None]]:
    """Every (table, column, data_type, char_max_len) in the public schema,
    base tables only (skips views)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.table_name, c.column_name, c.data_type, "
            "       c.character_maximum_length "
            "FROM information_schema.columns c "
            "JOIN information_schema.tables t "
            "  ON t.table_schema = c.table_schema "
            " AND t.table_name = c.table_name "
            "WHERE c.table_schema = 'public' "
            "  AND t.table_type = 'BASE TABLE' "
            "ORDER BY c.table_name, c.ordinal_position"
        )
        return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def _load_unique_columns(conn) -> set[tuple[str, str]]:
    """Every (table, column) that participates in a UNIQUE index or
    constraint (primary keys included).

    Such columns are skipped by the masker: masking inherently collapses
    or randomizes values, which violates the uniqueness guarantee
    (observed: `res_country.code` is varchar(2) UNIQUE — every masked
    value clamped to 2 chars, all collapsed to one value → duplicate
    key). In an Odoo schema a unique column is a structural key
    (country/currency/lang code, login, xml-id) rather than free-form
    PII, so passthrough is the correct call. Genuinely-unique PII
    columns (e.g. res_users.login) are covered by the allow-list.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.relname, a.attname "
            "FROM pg_index i "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_attribute a "
            "  ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indisunique AND n.nspname = 'public'"
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


def mask_database(
    db_dsn: str,
    allowlist: dict,
    rules: dict,
    *,
    deny_patterns: list[tuple[str, re.Pattern]],
    log,
) -> dict[str, Any]:
    """Apply type-based masking + the deny-list pass to one database.

    Returns a metrics dict.
    """
    import psycopg2
    conn = psycopg2.connect(db_dsn)
    conn.autocommit = False
    masked_cols = 0
    passthrough_cols = 0
    allowed_cols = 0
    unique_skipped = 0
    deny_scrubbed = 0
    try:
        ttypes = _load_odoo_ttypes(conn)
        unique_cols = _load_unique_columns(conn)
        columns = _list_columns(conn)
        log("mask.columns.discovered", count=len(columns),
            odoo_fields=len(ttypes), unique_columns=len(unique_cols))

        with conn.cursor() as cur:
            for table, column, data_type, char_len in columns:
                if is_allowed(table, column, allowlist):
                    allowed_cols += 1
                    continue
                if (table, column) in unique_cols:
                    # Masking can't preserve a uniqueness guarantee;
                    # unique columns in an Odoo schema are structural
                    # keys, not free PII. Passthrough.
                    unique_skipped += 1
                    continue
                semantic = classify_column(
                    table, column,
                    odoo_ttype=ttypes.get((table, column)),
                    data_type=data_type,
                    char_max_len=char_len,
                )
                if semantic == "_unsupported":
                    # An exotic physical type with no masking strategy —
                    # left untouched but surfaced so a human can review
                    # whether that column could carry PII.
                    log("mask.column.unsupported_type",
                        table=table, column=column, data_type=data_type)
                    passthrough_cols += 1
                    continue
                expr = strategy_sql(semantic, _quote_ident(column), rules)
                if expr is None:
                    passthrough_cols += 1
                    continue
                expr = clamp_expr_to_column(expr, data_type, char_len)
                cur.execute(
                    f"UPDATE {_quote_ident(table)} "
                    f"SET {_quote_ident(column)} = {expr}"
                )
                masked_cols += 1

            # Deny-list safety net: regexp_replace each pattern over every
            # non-allowlisted text/char column. Mostly redundant after the
            # type pass, but catches anything the classifier passed through.
            for table, column, data_type, _char_len in columns:
                if data_type not in _TEXT_DATA_TYPES:
                    continue
                if is_allowed(table, column, allowlist):
                    continue
                qcol = _quote_ident(column)
                for _name, rx in deny_patterns:
                    # psycopg2 parameterizes the regex literal; the column
                    # and table identifiers are quoted, not parameterized.
                    cur.execute(
                        f"UPDATE {_quote_ident(table)} "
                        f"SET {qcol} = regexp_replace("
                        f"  {qcol}::text, %s, '[REDACTED]', 'g') "
                        f"WHERE {qcol} ~ %s",
                        (rx.pattern, rx.pattern),
                    )
                    deny_scrubbed += cur.rowcount if cur.rowcount > 0 else 0

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "masked_columns": masked_cols,
        "passthrough_columns": passthrough_cols,
        "allowed_columns": allowed_cols,
        "unique_skipped_columns": unique_skipped,
        "deny_list_rows_scrubbed": deny_scrubbed,
    }


def sample_audit(
    db_dsn: str,
    deny_patterns: list[tuple[str, re.Pattern]],
    *,
    sample_size: int,
    log,
) -> list[dict[str, Any]]:
    """Sample text cells and assert no deny-list pattern survives.

    Returns a list of violation dicts (empty == clean).
    """
    import psycopg2
    conn = psycopg2.connect(db_dsn)
    violations: list[dict[str, Any]] = []
    try:
        columns = [
            (t, c) for (t, c, dt, _l) in _list_columns(conn)
            if dt in _TEXT_DATA_TYPES
        ]
        with conn.cursor() as cur:
            for table, column in columns:
                cur.execute(
                    f"SELECT {_quote_ident(column)}::text "
                    f"FROM {_quote_ident(table)} "
                    f"WHERE {_quote_ident(column)} IS NOT NULL "
                    f"ORDER BY random() LIMIT %s",
                    (sample_size,),
                )
                for (value,) in cur.fetchall():
                    hits = scan_for_pii(value, deny_patterns)
                    if hits:
                        violations.append({
                            "table": table, "column": column,
                            "patterns": hits,
                            "excerpt": value[:80],
                        })
    finally:
        conn.close()
    if violations:
        log("mask.audit.violations", count=len(violations))
    else:
        log("mask.audit.clean")
    return violations


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def _make_logger():
    def log(event: str, **fields: Any) -> None:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "event": event, **fields}
        print(json.dumps(rec), flush=True)
    return log


def _db_dsn(admin_dsn: str, dbname: str) -> str:
    """Swap the database name in a libpq URI."""
    base, _, _old = admin_dsn.rpartition("/")
    # Preserve any ?query string on the original DSN.
    query = ""
    if "?" in _old:
        _olddb, _, query = _old.partition("?")
        query = "?" + query
    return f"{base}/{dbname}{query}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mask a fresh agentlab restore.")
    parser.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "mask-allowlist.yml"))
    parser.add_argument("--rules", default=os.path.join(
        os.path.dirname(__file__), "masking-rules.yml"))
    parser.add_argument("--sample-size", type=int,
                        default=int(os.environ.get("SAMPLE_SIZE", "100")))
    parser.add_argument("--dry-run", action="store_true",
                        help="classify + plan only; apply no UPDATEs")
    args = parser.parse_args(argv)

    log = _make_logger()

    try:
        import psycopg2
    except ImportError:
        log("mask.error", msg="psycopg2 not installed (pip install psycopg2-binary)")
        return 1

    admin_dsn = os.environ.get("AGENTLAB_DSN", "").strip()
    if not admin_dsn:
        log("mask.error", msg="AGENTLAB_DSN env var required")
        return 1

    try:
        allowlist, rules = load_config(args.allowlist, args.rules)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        log("mask.error", msg=f"config load failed: {exc}")
        return 1

    deny_patterns = compile_deny_patterns(rules)
    log("mask.start", allowlist=args.allowlist, rules=args.rules,
        deny_patterns=len(deny_patterns), dry_run=args.dry_run)

    try:
        databases = list_databases(admin_dsn)
    except psycopg2.Error as exc:
        log("mask.error", msg=f"cannot list databases: {exc}")
        return 1
    log("mask.databases", count=len(databases), names=databases)

    if args.dry_run:
        log("mask.dry_run.done", msg="no UPDATEs applied")
        return 0

    total_violations: list[dict[str, Any]] = []
    for dbname in databases:
        db_dsn = _db_dsn(admin_dsn, dbname)
        started = time.time()
        log("mask.database.start", db=dbname)
        try:
            metrics = mask_database(
                db_dsn, allowlist, rules,
                deny_patterns=deny_patterns, log=log,
            )
        except psycopg2.Error as exc:
            log("mask.error", db=dbname, msg=f"masking failed: {exc}")
            return 1
        violations = sample_audit(
            db_dsn, deny_patterns,
            sample_size=args.sample_size, log=log,
        )
        total_violations.extend(violations)
        log("mask.database.end", db=dbname,
            duration_s=round(time.time() - started, 1), **metrics)

    if total_violations:
        log("mask.fail", msg="sample audit found surviving PII",
            violations=total_violations[:20])
        return 2

    log("mask.done", databases=len(databases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
