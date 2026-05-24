# Writing addon tests

Reference for adding tests to a `custom-addons/<addon>/` Odoo module
in this monorepo. Covers the Odoo test taxonomy, our project's
conventions, and the pitfalls that have bitten us in CI.

---

## 1. Which base class?

| Class | Use when | Notes |
|---|---|---|
| `odoo.tests.TransactionCase` | The default. ORM-only unit tests; no HTTP. | Each method runs in its own transaction; the transaction is rolled back at teardown. |
| `odoo.tests.SavepointCase` | Multiple tests in one class share an expensive setup. | `setUpClass` creates fixtures inside a savepoint; each test gets a nested savepoint. Faster than per-test fixtures when setup is heavy. |
| `odoo.tests.HttpCase` | You're testing HTTP routes or anything that uses the HTTP request stack (controllers, sessions, redirects). | Requires a running HTTP server — Odoo runs one for the test. See §3 for the CI tag pattern. |
| `odoo.tests.SingleTransactionCase` | All tests in the class share ONE transaction (no rollback between them). | Rare. Use only when ordering is essential and a savepoint isn't enough. |
| `odoo.tests.BaseCase` | Almost never. Bypasses the transaction handling that makes Odoo tests safe. | Don't use unless you know exactly why. |

**Default:** `TransactionCase`. Reach for the others only when the
default is insufficient.

---

## 2. Where does the test live?

```
custom-addons/<addon>/
├── __manifest__.py
├── models/
├── tests/
│   ├── __init__.py            # <— SEE §4
│   ├── test_models.py
│   ├── test_http_routes.py
│   └── test_security.py
└── ...
```

- **One file per concern.** `test_models.py`, `test_security.py`,
  `test_<view>.py` — easier to navigate than one mega-file.
- **`test_` prefix mandatory.** Odoo's runner only discovers
  `test_*.py` files.
- **Classes start with `Test`.** Same convention; not enforced by the
  runner but enforced by code review.

---

## 3. Tag semantics — the trap

Every Odoo test class can be tagged with `@tagged(...)`. The two tags
most relevant here:

- **`at_install`** — runs immediately after the addon installs.
  The default if no tag is specified.
- **`post_install`** — runs only after ALL addons in the test run
  have installed. Use for tests that need other modules' models
  fully wired (e.g. anything that touches `account` from a non-
  `account` addon).

### The CI tag pattern

Our HttpCase job (`.github/workflows/ci.yml::test-addon-httpcase`)
runs:

```bash
odoo --test-tags "/<addon>" --workers=0
```

`"/<addon>"` matches every test tagged with the addon's name (Odoo
auto-tags by module name). The `--workers=0` switch is mandatory
for HttpCase — it starts the `ThreadedServer` which has the `.httpd`
attribute HttpCase needs.

### The trap

Earlier our HttpCase job ran:

```bash
odoo --test-tags "/<addon>,-post_install"
```

— intending to "include this addon, exclude post-install class". But
every meaningful test in our `saas_tenant_gate` addon is tagged
`post_install`. The negation matched ALL of them, so the job ran 0
tests and silently passed (`0 post-tests in 0.02s`). Took an
incident to spot. **Don't write tag expressions with negations
unless you've explicitly counted the included tests in CI logs.**

---

## 4. `tests/__init__.py` — the I001 trap

Every addon's `tests/__init__.py` imports its test modules so Odoo's
runner discovers them:

```python
# ✅ CORRECT — one combined import (ruff isort canonical)
from . import test_http_routes, test_models, test_security
```

NOT:

```python
# ❌ WRONG — ruff I001 will fail your PR
from . import test_models
from . import test_security
from . import test_http_routes
```

This bit us repeatedly during Tier-7 (PR #36, PR #37) — when the
implementation agent added a new test, it wrote a separate
`from . import test_<spec>` line, which tripped `lint-addons` and
escalated the PR. Fixed structurally at the agent layer (Tier-7
follow-up commit `4b80156` runs `ruff --select I --fix` after every
session sync), but the canonical form here is still:

> one `from . import` line, alphabetised, comma-separated names.

---

## 5. Fixture patterns

### Per-test fixtures (default)

```python
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWidgetSecurity(TransactionCase):

    def setUp(self):
        super().setUp()
        # New affiliates per test; rolled back at teardown.
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.user = self._make_test_user()

    def _make_test_user(self):
        # Helper kept as a method, not a fixture — it reads
        # like Python and shows up in stack traces.
        return self.env['res.users'].create({
            'login': 'tu_test@example.com',
            'name': 'Test User',
        })
```

### Shared expensive setup (SavepointCase)

```python
from odoo.tests import SavepointCase, tagged


@tagged('post_install', '-at_install')
class TestWidgetReports(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Runs ONCE for the class — expensive seed of 1000 records.
        cls.company = cls.env['res.company'].create({'name': 'X'})
        cls.affiliates = cls.env['club.affiliate'].create(
            [{'name': f'A{i}', 'company_id': cls.company.id} for i in range(1000)]
        )
```

`SavepointCase`'s class-level setup runs inside a savepoint that is
released only after the class finishes; per-test savepoints nest
inside it. Don't mutate the class-level fixtures inside a test
unless you can tolerate the mutation leaking through the savepoint
boundary.

---

## 6. Mocking

Two camps, very different semantics.

### Mock the model (most common)

```python
from unittest.mock import patch
from odoo.tests import TransactionCase


class TestPaymentFlow(TransactionCase):

    def test_charges_call_stripe(self):
        with patch.object(
            self.env['payment.provider'].__class__,
            '_charge_card',
            return_value={'status': 'succeeded', 'id': 'pi_x'},
        ) as mock_charge:
            order = self.env['sale.order'].browse(1)
            order.action_capture()
            mock_charge.assert_called_once_with(order.partner_id)
```

`patch.object` on the registered class — patches across the recordset,
so any code path through `payment.provider._charge_card` is intercepted.

### Mock an external HTTP call (`responses` for `requests`)

```python
import responses
from odoo.tests import TransactionCase


class TestUpstreamSync(TransactionCase):

    @responses.activate
    def test_pulls_remote_inventory(self):
        responses.add(
            responses.GET,
            'https://upstream.example/inventory',
            json={'items': [{'sku': 'X', 'qty': 4}]},
            status=200,
        )
        self.env['inventory.sync'].pull()
        items = self.env['stock.item'].search([('sku', '=', 'X')])
        self.assertEqual(items.quantity, 4)
```

**Don't reach into the transport directly** (e.g. `urllib3.connectionpool`).
The `responses` / `httpx_mock` / `respx` libraries are mature; one
will cover the HTTP library your code uses.

### What NOT to mock

- The ORM (`self.env`, `recordset.read`, etc). Use real records.
- `datetime.now` — use `freezegun` instead: `@freeze_time('2026-01-01')`.

---

## 7. Common pitfalls (incident-driven)

### `--stop-after-init` doesn't run HttpCase tests

The `test-addon` job runs `odoo --init <addon> --stop-after-init`
which exits before the HTTP server starts. Use `test-addon-httpcase`
(workers=0, `--test-tags '/<addon>'`) for HTTP route tests. The
`test-addon` job is a build-test bootstrap; it verifies install
succeeds but exercises no test logic.

### `--test-enable` only runs `at_install` by default

```bash
odoo --init my_addon --test-enable        # runs only at_install tests
odoo --test-tags "post_install" -d db     # runs only post_install tests
```

If a test isn't running, check its tag. The `--test-tags` flag is
your source of truth.

### Empty recordset is not an error

```python
record = self.env['model'].browse(99999)  # nothing at id 99999
print(record.name)   # AttributeError? NO — returns ''
print(bool(record))  # False — falsy
```

`browse` on a missing id returns an empty recordset, not `None` and
not an error. Always `if not record:` to detect a missing row.

### `self.env.ref('xml_id')` raises `ValueError` if the xml_id is missing

— but the error message is laconic. Add a clearer assertion in the
test or use `self.env.ref('xml_id', raise_if_not_found=False)` and
check explicitly.

### Don't rely on `commit()` inside a test

Your transaction is rolled back at teardown. Anything you `commit()`
will be flushed and you'll fight cleanup. Use `flush()` instead if
you need the SQL to actually go through.

---

## 8. Running locally

```bash
# Install dev deps once:
pip install pytest

# Pull a fresh image — matches CI:
docker pull odoo:19.0

# Run the test you care about:
docker run --rm \
  -e PGHOST=host.docker.internal \
  -e PGUSER=odoo -e PGPASSWORD=odoo \
  -v "$PWD/custom-addons:/mnt/extra-addons:ro" \
  odoo:19.0 \
  odoo --init my_addon --test-enable --stop-after-init \
       -d test_db --workers=0
```

`pytest custom-addons/my_addon/tests/` does NOT work — Odoo's
runner is the only environment where `self.env` and the registry
exist. If you want pytest-style discovery, use `odoo-pytest` /
`pytest-odoo` — but our project's CI runs the native Odoo runner.

---

## 9. Adding a test in a fix-brief

The fix-brief template (`docs/superpowers/specs/_TEMPLATE-fix.md`
§6) requires a regression test. The minimum diff:

```python
# custom-addons/my_addon/tests/test_<change>.py
import unittest  # noqa: F401 — `unittest.TestCase` not used; remove if unused.

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRegression(TransactionCase):

    def test_<bug>_does_not_recur(self):
        # Recreate the exact path the bug took.
        ...
```

Then update `custom-addons/my_addon/tests/__init__.py` to import
the new test module — combined-line form (§4). The `lint-addons`
ruff job will fail your PR otherwise.

The implementation agent itself does this automatically when running
a fix-brief through `/speckit.fix` — the `auto_isort` hook in
`Coder._sync_from_session` resolves the I001 the LLM otherwise
introduces.

---

## 10. References

- Odoo 19 testing docs: https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html
- The HttpCase pitfall write-up: this repo's incident log, commit
  fixing `saas_tenant_gate` HttpCase suite execution.
- ruff isort config: `pyproject.toml` `[tool.ruff.lint.isort]` —
  matches what `lint-addons` runs in CI.
