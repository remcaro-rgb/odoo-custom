#!/usr/bin/env python3
"""mask_prod_data.py — apply masking to a fresh agentlab restore.

Implements docs/superpowers/specs/2026-05-16-agentlab-environment-design.md §5.1.

Pipeline, per database in the agentlab Postgres cluster:

  1. Load ir_model_fields → the Odoo field type (ttype) for every
     (table, column). This is the authoritative classifier input —
     far more reliable than guessing from information_schema data types
     (it distinguishes selection from char, monetary from float, etc.).
  2. Enumerate every column via information_schema.
  3. For each column NOT in a structural ORM-metadata table (see
     _STRUCTURAL_TABLES — masking those corrupts the ORM) and NOT in
     mask-allowlist.yml:
       - classify it to a masking-rules semantic type
       - apply the strategy as a single SQL UPDATE (set-based, fast)
  4. Run the universal deny-list regexp pass over non-allowlisted
     text/char columns as a safety net for classifier gaps.
  5. Sample rows and assert no deny-list PII pattern survives.
  6. Smoke-check that the structural tables carry no masker markers (a
     masked framework table would break `odoo -u all`); fail if any do.
  7. Emit structured JSON metrics on stdout.

Transient connection drops over the flyctl-proxy tunnel are retried per
database (TCP keepalives + bounded retry), since they roll back cleanly.

Masking is done with set-based SQL UPDATEs (not row-by-row in Python)
so a 5 GB database completes in minutes, not hours. The pure helper
functions — classify_column, strategy_sql, is_allowed, is_structural_table,
scan_for_pii — carry no DB dependency and are unit-tested in
tests/test_masking.py.

Exit codes:
  0  masking applied, sample audit + structural smoke clean
  1  configuration / connection error
  2  surviving PII in the sample audit, OR a structural table was masked
     (either way the masked snapshot is not safe to trust / can't load)
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

# pg_catalog `pg_type.typname` → the information_schema-style `data_type`
# string that classify_column expects. Column types are read straight from
# pg_catalog (not information_schema) because information_schema was observed
# to misreport a jsonb column's data_type, so the physical-type guard in
# classify_column fell through and a json column got a text strategy
# (`ir_filters.sort` → "invalid input syntax for type json"). pg_catalog is
# the source of truth information_schema is itself a view over. Any typname
# not in this map passes through unchanged → classify_column routes it to
# `_unsupported` (safe passthrough).
_PG_TYPE_TO_DATA_TYPE = {
    "bool": "boolean",
    "int2": "smallint", "int4": "integer", "int8": "bigint",
    "float4": "real", "float8": "double precision",
    "numeric": "numeric",
    "bpchar": "character", "varchar": "character varying",
    "text": "text", "citext": "citext", "name": "name",
    "json": "json", "jsonb": "jsonb", "bytea": "bytea",
    "date": "date",
    "timestamp": "timestamp without time zone",
    "timestamptz": "timestamp with time zone",
    "time": "time without time zone",
    "timetz": "time with time zone",
}

# Odoo ttypes that never carry PII — masking them would corrupt referential
# integrity (FKs / reference pointers) or break enum/boolean semantics.
_PASSTHROUGH_TTYPES = frozenset({
    "many2one", "one2many", "many2many", "reference",
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

# Odoo ORM-structural metadata tables. These hold framework definitions —
# model names, field names/ttypes, xml-id → model/res_id mappings, module
# manifests, relation + constraint names — never tenant PII. Masking any of
# them corrupts the ORM: hashing ir_model_data.model turns an xml-id's target
# model into "MASKED:<hash>", so the next `odoo -u all` (module upgrade) dies
# re-resolving xml-ids with `KeyError: 'MASKED:...'` (see issue #140). The
# (module, name) columns are spared only because they sit in a UNIQUE index;
# `model` and others are not, so an explicit table-level skip is needed.
#
# Deliberately an explicit allow-list of structural tables, NOT a blanket
# `ir_*` skip: other ir_ tables DO carry PII or secrets and must stay masked
# (ir_attachment file blobs/names, ir_mail_server smtp_user/smtp_pass,
# ir_config_parameter values, ir_logging messages, ...).
#
# The ir_ui_* / ir_act* group below holds UI + action *definitions* that
# `odoo -u all` rewrites from each module's XML. Masking them corrupts the
# load — e.g. a hashed ir.ui.menu.action reference ("MASKED:<hash>,5") fails
# with `ValueError: Wrong value for ir.ui.menu.action` (see issue #142).
# These are framework/config definitions (menus, views, window/server/report
# actions), not tenant business PII.
_STRUCTURAL_TABLES = frozenset({
    # Core ORM metadata (#140).
    "ir_model_data",
    "ir_model",
    "ir_model_fields",
    "ir_model_fields_selection",
    "ir_model_relation",
    "ir_model_constraint",
    "ir_module_module",
    "ir_module_module_dependency",
    # UI + action definitions rewritten by `-u all` (#142).
    "ir_ui_menu",
    "ir_ui_view",
    "ir_ui_view_custom",
    "ir_actions",  # base ir.actions.actions table (real name; NOT ir_actions_actions)
    "ir_act_window",
    "ir_act_window_view",
    "ir_act_url",
    "ir_act_server",
    "ir_act_report_xml",
    "ir_act_client",
})


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


def is_structural_table(table: str) -> bool:
    """True for Odoo ORM-framework metadata tables that must never be masked.

    Masking these corrupts model / field / xml-id / module resolution, which
    breaks any subsequent `odoo -u all` (module upgrade). See `_STRUCTURAL_TABLES`
    and issue #140.
    """
    return table in _STRUCTURAL_TABLES


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
        if odoo_ttype in ("many2one", "one2many", "many2many", "reference"):
            # `reference` is a typed pointer stored as "model,id" — a
            # polymorphic FK. Masking it corrupts the pointer and breaks
            # `odoo -u all` (e.g. ir.ui.menu.action), and it never carries
            # PII. Passthrough, same as the relational ttypes. See #142.
            return "foreign_key"
        if odoo_ttype == "selection":
            return "selection"
        if odoo_ttype in ("text", "html"):
            return "text"
        if odoo_ttype == "char":
            return "string"
        # binary/json ttype but a textual physical column, or any other
        # ttype — redact via the long-string path. (reference handled above.)
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


def is_masked_value(value: str | None) -> bool:
    """True when a cell is recognizably this masker's own replacement output.

    The sample audit re-scans masked columns with the deny-list patterns;
    the replacements themselves can match (`user…@masked.invalid` is an
    Email-like hit) and would otherwise register as surviving PII. A value
    in the masker's own output shape is masked-by-definition, not a leak.
    """
    if not value:
        return False
    v = value.strip()
    return (
        v.startswith("MASKED:")
        or v.startswith("[REDACTED")
        or v == "+57XXXXXXXXXX"
        or "@masked.invalid" in v
    )


# --------------------------------------------------------------------------
# DB layer — impure
# --------------------------------------------------------------------------

def _quote_ident(name: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes."""
    return '"' + name.replace('"', '""') + '"'


# libpq TCP keepalives. Masking runs for minutes per database over a
# `flyctl proxy` tunnel to the agentlab Postgres; without keepalives the
# socket can be torn down mid-run and the next statement fails with
# "connection already closed" (see issue #143). These keep the kernel
# probing the peer so a transient idle/NAT drop is detected + kept alive.
_KEEPALIVE_KW = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
}


def _connect(dsn: str):
    """psycopg2.connect with TCP keepalives applied (see _KEEPALIVE_KW)."""
    import psycopg2
    return psycopg2.connect(dsn, **_KEEPALIVE_KW)


# Databases that must never be masked:
#   postgres / template0 / template1 — Postgres-internal.
#   repmgr — Fly flex-Postgres's replication-metadata DB. Running mask
#            UPDATEs over its tables corrupts cluster replication. The
#            agentlab Postgres is a --flex cluster, so repmgr always
#            exists there.
_INTERNAL_DATABASES = ("postgres", "template0", "template1", "repmgr")


def list_databases(admin_dsn: str) -> list[str]:
    """Every database in the cluster except internal ones + templates."""
    conn = _connect(admin_dsn)
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
    ordinary tables only (skips views, partitions, system tables).

    Column types are read from pg_catalog rather than information_schema:
    the latter was observed to misreport a jsonb column, defeating the
    physical-type guard in classify_column. `typname` is normalised to the
    information_schema-style string classify_column expects; an unknown
    typname is passed through verbatim and lands in the `_unsupported`
    branch. char_max_len is recovered from atttypmod for varchar/char.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.relname, a.attname, t.typname, "
            "       CASE WHEN a.atttypmod >= 4 "
            "            AND t.typname IN ('varchar', 'bpchar') "
            "            THEN a.atttypmod - 4 END "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "WHERE n.nspname = 'public' "
            "  AND c.relkind = 'r' "
            "  AND a.attnum > 0 "
            "  AND NOT a.attisdropped "
            "ORDER BY c.relname, a.attnum"
        )
        return [
            (r[0], r[1],
             _PG_TYPE_TO_DATA_TYPE.get(r[2], (r[2] or "").lower()),
             r[3])
            for r in cur.fetchall()
        ]


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
    import psycopg2  # noqa: F401  (used by the per-column SAVEPOINT handler)
    conn = _connect(db_dsn)
    conn.autocommit = False
    masked_cols = 0
    passthrough_cols = 0
    allowed_cols = 0
    unique_skipped = 0
    structural_skipped = 0
    deny_scrubbed = 0
    try:
        ttypes = _load_odoo_ttypes(conn)
        unique_cols = _load_unique_columns(conn)
        columns = _list_columns(conn)
        log("mask.columns.discovered", count=len(columns),
            odoo_fields=len(ttypes), unique_columns=len(unique_cols))

        # Every per-column mutation runs inside its own SAVEPOINT. A
        # column that fails (an unforeseen type/constraint clash) is
        # rolled back to the savepoint and recorded — the rest of the
        # database is still masked, and the run reports EVERY bad column
        # at once instead of aborting on the first. If any column failed
        # the whole transaction is rolled back at the end (no
        # partially-masked data is ever committed) and the caller fails.
        failures: list[dict[str, Any]] = []

        def _run(cur, sql: str, params=None, *, table: str, column: str,
                 phase: str) -> bool:
            cur.execute("SAVEPOINT col_sp")
            try:
                cur.execute(sql, params)
            except psycopg2.Error as exc:
                cur.execute("ROLLBACK TO SAVEPOINT col_sp")
                failures.append({
                    "table": table, "column": column, "phase": phase,
                    "error": str(exc).strip().splitlines()[0],
                })
                return False
            cur.execute("RELEASE SAVEPOINT col_sp")
            return True

        with conn.cursor() as cur:
            for table, column, data_type, char_len in columns:
                if is_structural_table(table):
                    # Odoo ORM framework metadata — masking it corrupts
                    # model/xml-id resolution and breaks `-u all` (#140).
                    structural_skipped += 1
                    continue
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
                ok = _run(
                    cur,
                    f"UPDATE {_quote_ident(table)} "
                    f"SET {_quote_ident(column)} = {expr}",
                    table=table, column=column, phase="type-strategy",
                )
                masked_cols += 1 if ok else 0

            # Deny-list safety net: regexp_replace each pattern over every
            # non-allowlisted text/char column. Mostly redundant after the
            # type pass, but catches anything the classifier passed through.
            for table, column, data_type, _char_len in columns:
                if data_type not in _TEXT_DATA_TYPES:
                    continue
                if is_structural_table(table):
                    # Same as the type pass — never touch ORM metadata (#140).
                    continue
                if is_allowed(table, column, allowlist):
                    continue
                if (table, column) in unique_cols:
                    # Same reason as the type pass — a regexp_replace can
                    # collapse two distinct values to the same redacted
                    # string and violate a UNIQUE constraint. Observed:
                    # ir_model_data.name (part of the (module,name) unique
                    # index) had its numeric suffix scrubbed by a deny
                    # pattern, colliding distinct xml-ids.
                    continue
                qcol = _quote_ident(column)
                for _name, rx in deny_patterns:
                    # psycopg2 parameterizes the regex literal; the column
                    # and table identifiers are quoted, not parameterized.
                    ok = _run(
                        cur,
                        f"UPDATE {_quote_ident(table)} "
                        f"SET {qcol} = regexp_replace("
                        f"  {qcol}::text, %s, '[REDACTED]', 'g') "
                        f"WHERE {qcol} ~ %s",
                        (rx.pattern, rx.pattern),
                        table=table, column=column, phase="deny-list",
                    )
                    if ok:
                        deny_scrubbed += cur.rowcount if cur.rowcount > 0 else 0

        if failures:
            # Don't commit a partially-masked database. Report every
            # failing column so they can all be fixed in one pass.
            conn.rollback()
            for f in failures:
                log("mask.column.failed", **f)
            raise RuntimeError(
                f"{len(failures)} column(s) failed masking in this database; "
                f"transaction rolled back"
            )

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
        "structural_skipped_columns": structural_skipped,
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
    conn = _connect(db_dsn)
    violations: list[dict[str, Any]] = []
    try:
        columns = [
            (t, c) for (t, c, dt, _l) in _list_columns(conn)
            if dt in _TEXT_DATA_TYPES and not is_structural_table(t)
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
                    if is_masked_value(value):
                        continue
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
        for v in violations:
            log("mask.audit.violation",
                table=v["table"], column=v["column"],
                patterns=v["patterns"], excerpt=v["excerpt"])
    else:
        log("mask.audit.clean")
    return violations


def verify_structural_integrity(
    db_dsn: str, *, sample_size: int, log,
) -> list[dict[str, Any]]:
    """Post-mask smoke: structural ORM tables must contain NO masker output.

    The structural-table skip (#140) is supposed to leave these framework
    tables untouched; if masker markers ("MASKED:", "[REDACTED") show up
    here, the skip regressed and `odoo -u all` will fail to load the masked
    snapshot (#140/#142). Cheap — only the (small) structural tables are
    sampled. Returns a list of violation dicts (empty == clean).

    Scope note: only structural *tables* are checked here. Reference-typed
    columns elsewhere are validated once reference passthrough lands (#142).
    """
    conn = _connect(db_dsn)
    violations: list[dict[str, Any]] = []
    try:
        columns = [
            (t, c) for (t, c, dt, _l) in _list_columns(conn)
            if dt in _TEXT_DATA_TYPES and is_structural_table(t)
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
                    if is_masked_value(value):
                        violations.append({
                            "table": table, "column": column,
                            "excerpt": value[:80],
                        })
                        break  # one hit per column is enough
    finally:
        conn.close()
    if violations:
        log("mask.structural.corrupted", count=len(violations))
        for v in violations:
            log("mask.structural.violation",
                table=v["table"], column=v["column"], excerpt=v["excerpt"])
    else:
        log("mask.structural.clean")
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


def _mask_database_with_retry(
    db_dsn: str, allowlist: dict, rules: dict, *,
    deny_patterns: list[tuple[str, re.Pattern]], log, dbname: str, attempts: int = 3,
) -> dict[str, Any]:
    """Run mask_database, retrying transient connection drops.

    A torn-down `flyctl proxy` tunnel surfaces as psycopg2
    OperationalError/InterfaceError ("connection already closed", #143). It's
    transient, and mask_database rolls the whole DB transaction back on
    failure, so a retry re-masks cleanly from the restored data. Deterministic
    failures (RuntimeError from a column clash) are NOT retried — they
    re-raise immediately for the caller to record.
    """
    import psycopg2
    for attempt in range(1, attempts + 1):
        try:
            return mask_database(
                db_dsn, allowlist, rules,
                deny_patterns=deny_patterns, log=log,
            )
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            if attempt >= attempts:
                raise
            first = (str(exc).strip().splitlines() or [exc.__class__.__name__])[0]
            log("mask.database.retry", db=dbname, attempt=attempt, error=first)
            time.sleep(2 ** attempt)


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
    structural_violations: list[dict[str, Any]] = []
    failed_databases: list[str] = []
    for dbname in databases:
        db_dsn = _db_dsn(admin_dsn, dbname)
        started = time.time()
        log("mask.database.start", db=dbname)
        try:
            metrics = _mask_database_with_retry(
                db_dsn, allowlist, rules,
                deny_patterns=deny_patterns, log=log, dbname=dbname,
            )
        except (psycopg2.Error, RuntimeError) as exc:
            # Keep going so a single run surfaces every failing column
            # across every database, instead of one bug per re-run.
            log("mask.error", db=dbname, msg=f"masking failed: {exc}")
            failed_databases.append(dbname)
            continue
        total_violations.extend(sample_audit(
            db_dsn, deny_patterns,
            sample_size=args.sample_size, log=log,
        ))
        structural_violations.extend(verify_structural_integrity(
            db_dsn, sample_size=args.sample_size, log=log,
        ))
        log("mask.database.end", db=dbname,
            duration_s=round(time.time() - started, 1), **metrics)

    if failed_databases:
        log("mask.fail", msg="masking failed for one or more databases",
            databases=failed_databases)
        return 1

    if structural_violations:
        log("mask.fail",
            msg="structural/framework tables contain masked values "
                "(would break `odoo -u all`)",
            violations=structural_violations[:20])
        return 2

    if total_violations:
        log("mask.fail", msg="sample audit found surviving PII",
            violations=total_violations[:20])
        return 2

    log("mask.done", databases=len(databases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
