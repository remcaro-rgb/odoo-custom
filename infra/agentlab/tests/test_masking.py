"""Unit tests for the pure helpers in mask_prod_data.py.

These cover the classification + strategy + scan logic that decides what
gets masked and how. The DB-layer functions (mask_database, sample_audit,
list_databases) are not exercised here — they need a live Postgres and
are validated by the agentlab-daily-restore workflow's dry-run.

Run: pytest infra/agentlab/tests/test_masking.py
"""

import os
import re

# sys.path is extended by conftest.py so this resolves to ../mask_prod_data.py
import mask_prod_data as m
import pytest

# --------------------------------------------------------------------------
# is_allowed
# --------------------------------------------------------------------------

def test_is_allowed_hit():
    allowlist = {"res_users": ["id", "login", "active"]}
    assert m.is_allowed("res_users", "login", allowlist) is True


def test_is_allowed_miss_column():
    allowlist = {"res_users": ["id", "login"]}
    assert m.is_allowed("res_users", "password", allowlist) is False


def test_is_allowed_miss_table():
    allowlist = {"res_users": ["id"]}
    assert m.is_allowed("res_partner", "id", allowlist) is False


def test_is_allowed_empty_allowlist():
    assert m.is_allowed("any", "thing", {}) is False


# --------------------------------------------------------------------------
# is_structural_table — ORM framework metadata must never be masked (#140)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("table", [
    "ir_model_data",
    "ir_model",
    "ir_model_fields",
    "ir_model_fields_selection",
    "ir_model_relation",
    "ir_model_constraint",
    "ir_module_module",
    "ir_module_module_dependency",
])
def test_is_structural_table_true(table):
    assert m.is_structural_table(table) is True


def test_is_structural_table_ir_model_data_specifically():
    # The exact table whose masked `model` column produced
    # `KeyError: 'MASKED:...'` during `odoo -u all` (#140).
    assert m.is_structural_table("ir_model_data") is True


@pytest.mark.parametrize("table", [
    # Other ir_ tables CAN carry PII / secrets and MUST stay masked —
    # the structural skip is an explicit list, not a blanket ir_* match.
    "ir_attachment",
    "ir_mail_server",
    "ir_config_parameter",
    "ir_logging",
    # Ordinary tenant tables.
    "res_partner",
    "res_users",
    "account_move",
    "sale_order",
])
def test_is_structural_table_false(table):
    assert m.is_structural_table(table) is False


def test_structural_table_short_string_would_otherwise_be_masked():
    # Guard the root cause: ir_model_data.model is a Char field, so
    # classify_column would route it to the hashing "string" strategy.
    # The structural-table skip in mask_database is what spares it; this
    # asserts the classifier itself still treats it as maskable so the
    # skip remains load-bearing.
    assert m.classify_column(
        "ir_model_data", "model",
        odoo_ttype="char", data_type="character varying", char_max_len=64,
    ) == "string"
    assert m.is_structural_table("ir_model_data") is True


# --------------------------------------------------------------------------
# classify_column — name hints win first
# --------------------------------------------------------------------------

@pytest.mark.parametrize("column,expected", [
    ("email", "email"),
    ("email_from", "email"),
    ("partner_email", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("fax", "phone"),
    ("vat", "nit"),
    ("tax_id", "nit"),
    ("cedula", "cedula"),
    ("identification_id", "cedula"),
    ("iban", "iban"),
    ("acc_number", "iban"),
    ("card_number", "payment_card"),
    ("credit_card", "payment_card"),
])
def test_classify_name_hints_override_ttype(column, expected):
    # Even though Odoo says it's a plain char field, the column name
    # pins the semantic type.
    got = m.classify_column(
        "res_partner", column,
        odoo_ttype="char", data_type="character varying", char_max_len=64,
    )
    assert got == expected


# --------------------------------------------------------------------------
# classify_column — ttype + physical type together (the real shape:
# information_schema always supplies a data_type)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ttype,data_type,expected", [
    # FK-ish ttypes are stored as integer columns → passthrough.
    ("many2one", "integer", "foreign_key"),
    ("one2many", "integer", "foreign_key"),
    ("many2many", "integer", "foreign_key"),
    # selection is a varchar column carrying a constrained enum.
    ("selection", "character varying", "selection"),
    # physical type decides these regardless of ttype.
    ("boolean", "boolean", "boolean"),
    ("date", "date", "date"),
    ("datetime", "timestamp without time zone", "date"),
    ("integer", "integer", "foreign_key"),
    # text columns: ttype refines char vs text/html.
    ("char", "character varying", "string"),
    ("text", "text", "text"),
    ("html", "text", "text"),
])
def test_classify_by_ttype(ttype, data_type, expected):
    got = m.classify_column(
        "res_partner", "some_field",
        odoo_ttype=ttype, data_type=data_type, char_max_len=None,
    )
    assert got == expected


def test_classify_boolean_column_named_email_is_boolean():
    # base_partner_merge_automatic_wizard.group_by_email — a boolean
    # toggle whose name contains 'email'. It crashed the real restore
    # because the name hint forced a text email strategy onto a boolean
    # column. Physical type must win.
    assert m.classify_column(
        "base_partner_merge_automatic_wizard", "group_by_email",
        odoo_ttype="boolean", data_type="boolean", char_max_len=None,
    ) == "boolean"


def test_classify_integer_column_named_phone_is_passthrough():
    # An integer 'phone_count' must not get the text phone strategy.
    assert m.classify_column(
        "some_table", "phone_count",
        odoo_ttype="integer", data_type="integer", char_max_len=None,
    ) == "foreign_key"


def test_classify_monetary_ttype_with_money_name():
    assert m.classify_column(
        "account_move", "amount_total",
        odoo_ttype="monetary", data_type="numeric", char_max_len=None,
    ) == "monetary"


def test_classify_float_ttype_without_money_name_is_passthrough():
    # A float that isn't money (e.g. a ratio) shouldn't get noise applied.
    assert m.classify_column(
        "product_template", "volume",
        odoo_ttype="float", data_type="numeric", char_max_len=None,
    ) == "foreign_key"


# --------------------------------------------------------------------------
# classify_column — physical type (bytea/json) overrides everything
# --------------------------------------------------------------------------

def test_classify_bytea_is_binary_via_data_type():
    # auth_totp_wizard.qrcode — the column that crashed the first real run.
    assert m.classify_column(
        "auth_totp_wizard", "qrcode",
        odoo_ttype="binary", data_type="bytea", char_max_len=None,
    ) == "binary"


def test_classify_bytea_beats_name_hint():
    # A bytea column literally named 'email' must still be binary — a
    # text-producing email strategy would crash on the bytea column.
    assert m.classify_column(
        "weird_table", "email_blob",
        odoo_ttype=None, data_type="bytea", char_max_len=None,
    ) == "binary"


def test_classify_binary_ttype():
    assert m.classify_column(
        "ir_attachment", "datas",
        odoo_ttype="binary", data_type="bytea", char_max_len=None,
    ) == "binary"


@pytest.mark.parametrize("dtype", ["json", "jsonb"])
def test_classify_json_via_data_type(dtype):
    # json and jsonb are distinct semantic types — the masking strategy
    # casts to the exact column type, so they must not be conflated.
    assert m.classify_column(
        "some_table", "config",
        odoo_ttype=None, data_type=dtype, char_max_len=None,
    ) == dtype


def test_classify_jsonb_column():
    # iap_service.description — the jsonb column that crashed restore #5.
    assert m.classify_column(
        "iap_service", "description",
        odoo_ttype="json", data_type="jsonb", char_max_len=None,
    ) == "jsonb"


# --------------------------------------------------------------------------
# classify_column — information_schema fallback (non-Odoo tables)
# --------------------------------------------------------------------------

def test_classify_fallback_boolean():
    assert m.classify_column(
        "some_m2m_rel", "flag",
        odoo_ttype=None, data_type="boolean", char_max_len=None,
    ) == "boolean"


def test_classify_fallback_short_varchar_is_string():
    assert m.classify_column(
        "raw_table", "code",
        odoo_ttype=None, data_type="character varying", char_max_len=16,
    ) == "string"


def test_classify_fallback_long_varchar_is_text():
    assert m.classify_column(
        "raw_table", "blurb",
        odoo_ttype=None, data_type="character varying", char_max_len=512,
    ) == "text"


def test_classify_fallback_integer_is_foreign_key():
    assert m.classify_column(
        "some_m2m_rel", "partner",
        odoo_ttype=None, data_type="integer", char_max_len=None,
    ) == "foreign_key"


def test_classify_unknown_physical_type_is_unsupported():
    # An exotic Postgres type with no masking strategy (uuid, arrays,
    # inet, ...). It must NOT be handed a text strategy — that would
    # crash the UPDATE. Classified _unsupported → passthrough + a
    # logged warning so a human can review it.
    assert m.classify_column(
        "raw_table", "weird", odoo_ttype=None,
        data_type="some_exotic_type", char_max_len=None,
    ) == "_unsupported"


def test_strategy_sql_unsupported_is_passthrough():
    assert m.strategy_sql("_unsupported", '"x"', {}) is None


# --------------------------------------------------------------------------
# strategy_sql
# --------------------------------------------------------------------------

@pytest.mark.parametrize("semantic", ["date", "boolean", "selection", "foreign_key"])
def test_strategy_sql_passthrough_returns_none(semantic):
    assert m.strategy_sql(semantic, '"col"', {}) is None


def test_strategy_sql_email_shape():
    sql = m.strategy_sql("email", '"email"', {})
    assert sql is not None
    assert "md5" in sql and "@masked.invalid" in sql
    # NULL-preserving.
    assert '"email" IS NULL THEN NULL' in sql


def test_strategy_sql_phone_constant():
    sql = m.strategy_sql("phone", '"phone"', {})
    assert "+57XXXXXXXXXX" in sql


def test_strategy_sql_text_keeps_length():
    sql = m.strategy_sql("text", '"notes"', {})
    assert "length(" in sql and "[REDACTED text length=" in sql


def test_strategy_sql_string_hashes_with_prefix():
    sql = m.strategy_sql("string", '"name"', {})
    assert "md5(" in sql and "MASKED:" in sql


def test_strategy_sql_monetary_uses_configured_range():
    rules = {"rules": {"monetary": {"range": 0.25}}}
    sql = m.strategy_sql("monetary", '"amount"', rules)
    # range 0.25 → multiplier between 0.75 and 1.25
    assert "0.75" in sql and "random()" in sql


def test_strategy_sql_monetary_default_range():
    sql = m.strategy_sql("monetary", '"amount"', {})
    # default range 0.10 → 0.9 .. 1.1
    assert "0.9" in sql


def test_strategy_sql_iban_and_card_redact():
    for st in ("iban", "payment_card"):
        sql = m.strategy_sql(st, '"x"', {})
        assert "[REDACTED]" in sql


def test_strategy_sql_binary_empties_to_bytea():
    sql = m.strategy_sql("binary", '"qrcode"', {})
    assert sql is not None
    assert "::bytea" in sql
    # NULL-preserving so a NOT NULL bytea column stays valid.
    assert '"qrcode" IS NULL THEN NULL' in sql
    # must NOT inject a text literal that a bytea column would reject
    assert "[REDACTED" not in sql


def test_strategy_sql_json_empties_to_object():
    sql = m.strategy_sql("json", '"settings"', {})
    assert sql is not None
    assert "{}" in sql
    # explicit ::json cast — a bare '{}' in a CASE resolves to text,
    # which won't assignment-cast into a json column.
    assert "::json" in sql
    assert '"settings" IS NULL THEN NULL' in sql


def test_strategy_sql_jsonb_casts_to_jsonb():
    sql = m.strategy_sql("jsonb", '"description"', {})
    assert sql is not None
    assert "::jsonb" in sql
    assert "{}" in sql


def test_strategy_sql_unknown_raises():
    with pytest.raises(ValueError):
        m.strategy_sql("not_a_strategy", '"x"', {})


# --------------------------------------------------------------------------
# clamp_expr_to_column — keep masked output inside a bounded varchar
# --------------------------------------------------------------------------

def test_clamp_wraps_bounded_varchar():
    # varchar(1) — the column type that crashed restore #6.
    out = m.clamp_expr_to_column("SOME_EXPR", "character varying", 1)
    assert out == "LEFT(SOME_EXPR, 1)"


def test_clamp_wraps_bounded_character():
    out = m.clamp_expr_to_column("E", "character", 8)
    assert out == "LEFT(E, 8)"


def test_clamp_noop_on_unbounded_varchar():
    # An unlimited varchar reports NULL character_maximum_length.
    assert m.clamp_expr_to_column("E", "character varying", None) == "E"


def test_clamp_noop_on_text():
    assert m.clamp_expr_to_column("E", "text", None) == "E"


def test_clamp_noop_on_non_text_types():
    # numeric / bytea / jsonb never receive text strategies, and LEFT()
    # would be invalid on them — clamp must leave them alone.
    for dt in ("numeric", "bytea", "jsonb", "integer"):
        assert m.clamp_expr_to_column("E", dt, 4) == "E"


# --------------------------------------------------------------------------
# deny-list scanning
# --------------------------------------------------------------------------

@pytest.fixture
def deny_patterns():
    rules = {
        "deny_list_patterns": [
            {"name": "Email-like",
             "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"},
            {"name": "IPv4",
             "regex": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"},
        ],
    }
    return m.compile_deny_patterns(rules)


def test_compile_deny_patterns_count(deny_patterns):
    assert len(deny_patterns) == 2
    assert all(isinstance(rx, re.Pattern) for _name, rx in deny_patterns)


def test_compile_deny_patterns_skips_entries_without_regex():
    patterns = m.compile_deny_patterns(
        {"deny_list_patterns": [{"name": "broken"}, {"regex": r"\d+"}]}
    )
    assert len(patterns) == 1


def test_scan_for_pii_finds_email(deny_patterns):
    hits = m.scan_for_pii("contact me at jane@example.com please", deny_patterns)
    assert "Email-like" in hits


def test_scan_for_pii_finds_multiple(deny_patterns):
    hits = m.scan_for_pii("mail x@y.co from 10.0.0.1", deny_patterns)
    assert set(hits) == {"Email-like", "IPv4"}


def test_scan_for_pii_clean_text(deny_patterns):
    assert m.scan_for_pii("MASKED:abc123 [REDACTED]", deny_patterns) == []


def test_scan_for_pii_empty(deny_patterns):
    assert m.scan_for_pii("", deny_patterns) == []
    assert m.scan_for_pii(None, deny_patterns) == []


# --------------------------------------------------------------------------
# is_masked_value — recognises the masker's own replacement output
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "MASKED:abcdef012345",
    # A masked reference value ("MASKED:<hash>,id") — the #142 token shape.
    # The structural smoke (verify_structural_integrity) relies on
    # is_masked_value to flag exactly this if a framework table regresses.
    "MASKED:d04ef9d99cd0,5",
    "[REDACTED]",
    "[REDACTED text length=42]",
    "+57XXXXXXXXXX",
    "user6f08ba43@masked.invalid",
    "  user6f08ba43@masked.invalid  ",
])
def test_is_masked_value_true(value):
    assert m.is_masked_value(value) is True


@pytest.mark.parametrize("value", [
    "jane@example.com",
    "image_1920",
    "l10n_din5008_sale",
    "+57 312 345 6789",
    "",
    None,
])
def test_is_masked_value_false(value):
    assert m.is_masked_value(value) is False


# --------------------------------------------------------------------------
# Phone-like deny pattern — must require a real (>=7-digit) phone number
# --------------------------------------------------------------------------

@pytest.fixture
def real_deny_patterns():
    here = os.path.dirname(__file__)
    _allowlist, rules = m.load_config(
        os.path.join(here, "..", "mask-allowlist.yml"),
        os.path.join(here, "..", "masking-rules.yml"),
    )
    return m.compile_deny_patterns(rules)


@pytest.mark.parametrize("technical_name", [
    "image_1920",
    "l10n_din5008_sale",
    "account_move_line_2024",
])
def test_phone_pattern_ignores_short_digit_runs(real_deny_patterns,
                                                technical_name):
    assert "Phone-like" not in m.scan_for_pii(technical_name,
                                              real_deny_patterns)


@pytest.mark.parametrize("phone", [
    "+57 312 345 6789",
    "3001234567",
    "601-234-5678",
])
def test_phone_pattern_matches_real_numbers(real_deny_patterns, phone):
    assert "Phone-like" in m.scan_for_pii(phone, real_deny_patterns)


# --------------------------------------------------------------------------
# load_config — exercised against the real committed config files
# --------------------------------------------------------------------------

def test_load_config_real_files():
    here = os.path.dirname(__file__)
    allowlist, rules = m.load_config(
        os.path.join(here, "..", "mask-allowlist.yml"),
        os.path.join(here, "..", "masking-rules.yml"),
    )
    # Spot-check the shape the masker depends on.
    assert "res_partner" in allowlist
    assert "id" in allowlist["res_partner"]
    assert "rules" in rules
    assert "deny_list_patterns" in rules


def test_load_config_rejects_missing_rules(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("not_rules: {}\n")
    allow = tmp_path / "allow.yml"
    allow.write_text("allowed: {}\n")
    with pytest.raises(ValueError):
        m.load_config(str(allow), str(bad))


# --------------------------------------------------------------------------
# end-to-end on the real config: every allowlisted column is real-looking,
# and every deny pattern compiles.
# --------------------------------------------------------------------------

def test_real_config_deny_patterns_all_compile():
    here = os.path.dirname(__file__)
    _allow, rules = m.load_config(
        os.path.join(here, "..", "mask-allowlist.yml"),
        os.path.join(here, "..", "masking-rules.yml"),
    )
    patterns = m.compile_deny_patterns(rules)
    assert len(patterns) >= 5  # email, phone, ipv4, ipv6, cedula, nit, card


def test_real_config_classify_known_pii_columns_get_masked():
    """The headline PII columns must NOT classify to a passthrough type."""
    here = os.path.dirname(__file__)
    _allow, rules = m.load_config(
        os.path.join(here, "..", "mask-allowlist.yml"),
        os.path.join(here, "..", "masking-rules.yml"),
    )
    passthrough = {"date", "boolean", "selection", "foreign_key"}
    for column, ttype in [
        ("name", "char"), ("email", "char"), ("phone", "char"),
        ("vat", "char"), ("street", "char"), ("comment", "text"),
    ]:
        semantic = m.classify_column(
            "res_partner", column,
            odoo_ttype=ttype, data_type="character varying", char_max_len=64,
        )
        assert semantic not in passthrough, f"{column} would leak (got {semantic})"
        assert m.strategy_sql(semantic, '"c"', rules) is not None
