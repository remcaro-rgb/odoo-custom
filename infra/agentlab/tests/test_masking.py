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
# classify_column — Odoo ttype is authoritative when no name hint
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ttype,expected", [
    ("many2one", "foreign_key"),
    ("one2many", "foreign_key"),
    ("many2many", "foreign_key"),
    ("selection", "selection"),
    ("boolean", "boolean"),
    ("date", "date"),
    ("datetime", "date"),
    ("integer", "foreign_key"),
    ("char", "string"),
    ("text", "text"),
    ("html", "text"),
])
def test_classify_by_ttype(ttype, expected):
    got = m.classify_column(
        "res_partner", "some_field",
        odoo_ttype=ttype, data_type=None, char_max_len=None,
    )
    assert got == expected


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


def test_classify_fallback_unknown_type_is_redacted():
    # Conservative default: anything unrecognized goes through the text
    # (redact) path rather than being left in the clear.
    assert m.classify_column(
        "raw_table", "weird", odoo_ttype=None,
        data_type="some_exotic_type", char_max_len=None,
    ) == "text"


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


def test_strategy_sql_unknown_raises():
    with pytest.raises(ValueError):
        m.strategy_sql("not_a_strategy", '"x"', {})


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
