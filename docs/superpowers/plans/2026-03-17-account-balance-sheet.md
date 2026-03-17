# account_balance_sheet Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `custom-addons/account_balance_sheet` — an Odoo 18 Community Balance Sheet report with a SQL-view model, list/pivot views, hierarchical PDF export grouped by PUC class, and Spanish translations.

**Architecture:** An `_auto=False` model backed by a PostgreSQL view (one row per posted journal entry line, PUC classes 1/2/3 only) follows the exact same pattern as `custom-addons/account_ledger_report`. An `AbstractModel` aggregates and sign-flips balances per account for the QWeb PDF template. Tests use the company's existing chart of accounts (skipped if PUC classes not present).

**Tech Stack:** Odoo 18 Community · Python 3.12 · PostgreSQL 15 · Docker Compose

---

## File Map

| File | Responsibility |
|---|---|
| `__init__.py` | Import models and report packages |
| `__manifest__.py` | Module metadata, data file list |
| `models/__init__.py` | Import model module |
| `models/account_balance_sheet.py` | `_auto=False` SQL view model |
| `report/__init__.py` | Import report model |
| `report/account_balance_sheet_report.py` | `AbstractModel` — `_get_report_values` aggregation + sign flip |
| `report/account_balance_sheet_template.xml` | QWeb PDF template + `ir.actions.report` binding |
| `views/account_balance_sheet_views.xml` | List, pivot, search views, action, menu |
| `security/ir.model.access.csv` | Read access for accounting groups |
| `tests/__init__.py` | Import test module |
| `tests/test_balance_sheet.py` | TransactionCase tests (model, date filter, equation) |
| `i18n/es.po` | Spanish (Spain) translations |
| `i18n/es_419.po` | Spanish (Latin America) translations |

All files live under `custom-addons/account_balance_sheet/`.

---

## Task 1: Module scaffold

**Files:**
- Create: `custom-addons/account_balance_sheet/__init__.py`
- Create: `custom-addons/account_balance_sheet/__manifest__.py`
- Create: `custom-addons/account_balance_sheet/models/__init__.py`
- Create: `custom-addons/account_balance_sheet/report/__init__.py`
- Create: `custom-addons/account_balance_sheet/tests/__init__.py`

- [ ] **Step 1: Create root `__init__.py`**

```python
from . import models
from . import report
```

- [ ] **Step 2: Create `__manifest__.py`**

```python
{
    'name': 'Balance Sheet Report',
    'version': '18.0.1.0.0',
    'summary': 'Live balance sheet report with PDF and Excel export',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_balance_sheet_views.xml',
        'report/account_balance_sheet_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

- [ ] **Step 3: Create `models/__init__.py`**

```python
from . import account_balance_sheet
```

- [ ] **Step 4: Create `report/__init__.py`**

```python
from . import account_balance_sheet_report
```

- [ ] **Step 5: Create `tests/__init__.py`**

```python
from . import test_balance_sheet
```

- [ ] **Step 6: Commit**

```bash
git add custom-addons/account_balance_sheet/
git commit -m "feat(account_balance_sheet): scaffold module skeleton"
```

---

## Task 2: SQL view model

**Files:**
- Create: `custom-addons/account_balance_sheet/models/account_balance_sheet.py`

- [ ] **Step 1: Create model**

```python
from odoo import fields, models, tools


class AccountBalanceSheet(models.Model):
    _name = 'account.balance.sheet'
    _description = 'Balance Sheet'
    _auto = False
    _order = 'account_code asc, id asc'
    _rec_name = 'move_name'

    _depends = {
        'account.move': ['name', 'date', 'state'],
        'account.move.line': [
            'move_id', 'account_id', 'partner_id',
            'debit', 'credit', 'company_id', 'parent_state',
        ],
        'account.account': ['code_store', 'name'],
        'res.company': ['currency_id'],
    }

    date = fields.Date(string='Date', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    account_code = fields.Char(string='Code', readonly=True)
    account_name = fields.Char(string='Account', translate=True, readonly=True)
    account_class = fields.Char(string='Class', readonly=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    move_name = fields.Char(string='Reference', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    debit = fields.Monetary(string='Debit', currency_field='currency_id', readonly=True)
    credit = fields.Monetary(string='Credit', currency_field='currency_id', readonly=True)
    balance = fields.Monetary(string='Balance', currency_field='currency_id', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute("""
            CREATE OR REPLACE VIEW %s AS (%s)
        """ % (self._table, self._table_query))

    @property
    def _table_query(self):
        return """
            SELECT
                aml.id                                                                    AS id,
                am.date                                                                   AS date,
                aml.account_id                                                            AS account_id,
                aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text)              AS account_code,
                aa.name                                                                   AS account_name,
                LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1)     AS account_class,
                aml.move_id                                                               AS move_id,
                am.name                                                                   AS move_name,
                aml.partner_id                                                            AS partner_id,
                aml.debit                                                                 AS debit,
                aml.credit                                                                AS credit,
                aml.debit - aml.credit                                                    AS balance,
                aml.company_id                                                            AS company_id,
                rc.id                                                                     AS currency_id
            FROM account_move_line aml
            JOIN account_move    am  ON am.id  = aml.move_id
            JOIN account_account aa  ON aa.id  = aml.account_id
            JOIN res_company     rco ON rco.id = aml.company_id
            JOIN res_currency    rc  ON rc.id  = rco.currency_id
            WHERE aml.parent_state = 'posted'
              AND LEFT(aa.code_store->>(SPLIT_PART(rco.parent_path, '/', 1)::text), 1)
                  IN ('1', '2', '3')
        """
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/models/account_balance_sheet.py
git commit -m "feat(account_balance_sheet): add SQL view model"
```

---

## Task 3: Security

**Files:**
- Create: `custom-addons/account_balance_sheet/security/ir.model.access.csv`

- [ ] **Step 1: Create security CSV**

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_account_balance_sheet_readonly,account.balance.sheet readonly,model_account_balance_sheet,account.group_account_readonly,1,0,0,0
access_account_balance_sheet_user,account.balance.sheet user,model_account_balance_sheet,account.group_account_user,1,0,0,0
access_account_balance_sheet_manager,account.balance.sheet manager,model_account_balance_sheet,account.group_account_manager,1,0,0,0
access_account_balance_sheet_system,account.balance.sheet system,model_account_balance_sheet,base.group_system,1,0,0,0
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/security/ir.model.access.csv
git commit -m "feat(account_balance_sheet): add security access rules"
```

---

## Task 4: Tests

**Files:**
- Create: `custom-addons/account_balance_sheet/tests/test_balance_sheet.py`

The tests use the company's existing chart of accounts. Accounts are located by `account_type` AND by code prefix (`1%`, `2%`, `3%`) to ensure they pass the SQL view's WHERE filter. The entire test class is skipped if no suitable accounts are found.

- [ ] **Step 1: Create test file**

```python
import unittest

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('account_balance_sheet', 'post_install', '-at_install')
class TestAccountBalanceSheet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        # Find accounts by type AND PUC code prefix so they pass the SQL view filter
        cls.account_activo = cls.env['account.account'].search([
            ('account_type', 'in', [
                'asset_receivable', 'asset_cash', 'asset_current',
                'asset_non_current', 'asset_prepayments',
            ]),
            ('code', '=like', '1%'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.account_pasivo = cls.env['account.account'].search([
            ('account_type', 'in', [
                'liability_payable', 'liability_current',
                'liability_non_current', 'liability_credit_card',
            ]),
            ('code', '=like', '2%'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.account_patrimonio = cls.env['account.account'].search([
            ('account_type', 'in', ['equity', 'equity_unaffected']),
            ('code', '=like', '3%'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        if not all([
            cls.account_activo, cls.account_pasivo,
            cls.account_patrimonio, cls.journal,
        ]):
            raise unittest.SkipTest(
                "No chart of accounts with PUC classes 1/2/3 found; "
                "skipping balance sheet tests."
            )

    def _post_move(self, date, lines):
        """Create and post a journal entry. lines = [(account, debit, credit), ...]"""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date,
            'line_ids': [
                (0, 0, {
                    'account_id': account.id,
                    'debit': debit,
                    'credit': credit,
                })
                for account, debit, credit in lines
            ],
        })
        move.action_post()
        return move

    def test_rows_appear_for_posted_entry(self):
        """Three lines of a balanced entry across classes 1/2/3 must appear."""
        move = self._post_move('2026-01-15', [
            (self.account_activo, 1000.0, 0.0),
            (self.account_pasivo, 0.0, 500.0),
            (self.account_patrimonio, 0.0, 500.0),
        ])
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        self.assertEqual(len(lines), 3)

    def test_account_class_is_first_digit_of_code(self):
        """account_class must equal the first character of account_code."""
        move = self._post_move('2026-01-15', [
            (self.account_activo, 1000.0, 0.0),
            (self.account_pasivo, 0.0, 500.0),
            (self.account_patrimonio, 0.0, 500.0),
        ])
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        for line in lines:
            self.assertEqual(
                line.account_class,
                line.account_code[0],
                f"Expected account_class={line.account_code[0]!r}, "
                f"got {line.account_class!r} for code {line.account_code!r}",
            )

    def test_balance_equals_debit_minus_credit(self):
        """balance must always equal debit - credit (no sign flip at model level)."""
        move = self._post_move('2026-01-15', [
            (self.account_activo, 1000.0, 0.0),
            (self.account_pasivo, 0.0, 500.0),
            (self.account_patrimonio, 0.0, 500.0),
        ])
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        for line in lines:
            self.assertAlmostEqual(
                line.balance, line.debit - line.credit,
                msg=f"balance != debit - credit for account {line.account_code}",
            )

    def test_accounting_equation_holds(self):
        """Sum of all raw balances must be zero for a balanced entry."""
        move = self._post_move('2026-01-15', [
            (self.account_activo, 1000.0, 0.0),
            (self.account_pasivo, 0.0, 500.0),
            (self.account_patrimonio, 0.0, 500.0),
        ])
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        total = sum(lines.mapped('balance'))
        self.assertAlmostEqual(total, 0.0, places=2,
            msg="Total balance must be zero for balanced entry")

    def test_draft_entries_excluded(self):
        """Draft entries must not appear in the view."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': '2026-01-15',
            'line_ids': [
                (0, 0, {'account_id': self.account_activo.id, 'debit': 100.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.account_pasivo.id, 'debit': 0.0, 'credit': 100.0}),
            ],
        })
        # deliberately NOT posted
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        self.assertEqual(len(lines), 0, "Draft entries must not appear")

    def test_date_cutoff_excludes_future_entries(self):
        """Entries dated after the cutoff must be excluded by domain filter."""
        move = self._post_move('2026-06-01', [
            (self.account_activo, 200.0, 0.0),
            (self.account_pasivo, 0.0, 200.0),
        ])
        lines_before = self.env['account.balance.sheet'].search([
            ('move_id', '=', move.id),
            ('date', '<=', '2026-05-31'),
        ])
        self.assertEqual(len(lines_before), 0, "Entry must be excluded before its date")

        lines_on = self.env['account.balance.sheet'].search([
            ('move_id', '=', move.id),
            ('date', '<=', '2026-06-01'),
        ])
        self.assertEqual(len(lines_on), 2, "Entry must appear on its exact date")

    def test_classes_all_present(self):
        """account_class values must be a subset of {'1', '2', '3'}."""
        move = self._post_move('2026-01-15', [
            (self.account_activo, 1000.0, 0.0),
            (self.account_pasivo, 0.0, 500.0),
            (self.account_patrimonio, 0.0, 500.0),
        ])
        lines = self.env['account.balance.sheet'].search([('move_id', '=', move.id)])
        classes = set(lines.mapped('account_class'))
        self.assertTrue(
            classes.issubset({'1', '2', '3'}),
            f"Unexpected account classes: {classes - {'1', '2', '3'}}",
        )
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/tests/test_balance_sheet.py
git commit -m "test(account_balance_sheet): add TransactionCase tests"
```

---

## Task 5: Views XML

**Files:**
- Create: `custom-addons/account_balance_sheet/views/account_balance_sheet_views.xml`

- [ ] **Step 1: Create views file**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- List View -->
    <record id="account_balance_sheet_view_list" model="ir.ui.view">
        <field name="name">account.balance.sheet.list</field>
        <field name="model">account.balance.sheet</field>
        <field name="arch" type="xml">
            <list string="Balance General"
                  create="false" edit="false" delete="false">
                <field name="account_class" optional="show"/>
                <field name="account_code" optional="show"/>
                <field name="account_name"/>
                <field name="account_id" column_invisible="1"/>
                <field name="move_name"/>
                <field name="partner_id"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="debit" sum="Total Debit"/>
                <field name="credit" sum="Total Credit"/>
                <field name="balance" sum="Total Balance"/>
            </list>
        </field>
    </record>

    <!-- Pivot View -->
    <record id="account_balance_sheet_view_pivot" model="ir.ui.view">
        <field name="name">account.balance.sheet.pivot</field>
        <field name="model">account.balance.sheet</field>
        <field name="arch" type="xml">
            <pivot string="Balance General" disable_linking="True">
                <field name="account_class" type="row"/>
                <field name="account_id" type="row"/>
                <field name="debit" type="measure"/>
                <field name="credit" type="measure"/>
                <field name="balance" type="measure"/>
            </pivot>
        </field>
    </record>

    <!-- Search View -->
    <record id="account_balance_sheet_view_search" model="ir.ui.view">
        <field name="name">account.balance.sheet.search</field>
        <field name="model">account.balance.sheet</field>
        <field name="arch" type="xml">
            <search string="Balance General">
                <field name="date" string="Al Corte De"
                       filter_domain="[('date', '&lt;=', self)]"/>
                <field name="account_id" string="Cuenta"/>
                <field name="partner_id" string="Contacto"/>
                <field name="move_id" string="Asiento"/>
                <separator/>
                <filter name="date_to"
                        string="Al Corte De (Hoy)"
                        domain="[('date', '&lt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <separator/>
                <filter name="class_activo" string="Activo"
                        domain="[('account_class', '=', '1')]"/>
                <filter name="class_pasivo" string="Pasivo"
                        domain="[('account_class', '=', '2')]"/>
                <filter name="class_patrimonio" string="Patrimonio"
                        domain="[('account_class', '=', '3')]"/>
                <group expand="0" string="Agrupar Por">
                    <filter name="group_by_account_class" string="Clase"
                            context="{'group_by': 'account_class'}"/>
                    <filter name="group_by_account" string="Cuenta"
                            context="{'group_by': 'account_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <!-- Action -->
    <record id="action_account_balance_sheet" model="ir.actions.act_window">
        <field name="name">Balance General</field>
        <field name="res_model">account.balance.sheet</field>
        <field name="view_mode">list,pivot</field>
        <field name="search_view_id" ref="account_balance_sheet_view_search"/>
        <field name="context">{
            'search_default_date_to': 1,
            'search_default_group_by_account_class': 1,
            'search_default_group_by_account': 1,
        }</field>
    </record>

    <!-- Menu: Accounting → Reporting → Balance General -->
    <menuitem id="menu_account_balance_sheet"
              name="Balance General"
              parent="account.menu_finance_reports"
              action="action_account_balance_sheet"
              sequence="101"/>

</odoo>
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/views/account_balance_sheet_views.xml
git commit -m "feat(account_balance_sheet): add list, pivot, search views and menu"
```

---

## Task 6: First install and test run

- [ ] **Step 1: Restart Odoo to pick up the new module**

```bash
docker compose restart odoo
```

Wait ~15 seconds for Odoo to start.

- [ ] **Step 2: Install the module and run tests**

```bash
docker compose run --rm odoo python /odoo/odoo-bin \
  -d odoo \
  -c /etc/odoo/odoo.conf \
  -u account_balance_sheet \
  --test-tags account_balance_sheet \
  --stop-after-init
```

Expected output: tests discovered, run, and passing. Look for:
```
... Ran N test(s) in X.XXXs
OK
```

If tests are **skipped** with "No chart of accounts with PUC classes 1/2/3 found": the sandbox DB lacks a Colombian chart of accounts. Install `l10n_co` or create PUC accounts manually and re-run.

If tests **fail**: read the traceback and fix the model/SQL before continuing.

- [ ] **Step 3: Verify module appears in Odoo UI**

Open http://localhost:8069 → Accounting → Reporting → Balance General. Confirm the view loads with list and pivot tabs.

---

## Task 7: PDF report model

**Files:**
- Create: `custom-addons/account_balance_sheet/report/account_balance_sheet_report.py`

**How the PDF is triggered:** The `ir.actions.report` (added in Task 8) has `binding_type=report`, which adds "Balance General" to the Action → Print dropdown in the list view. The user first selects all visible records (header checkbox → "Select all N records"), then clicks Action → Print → Balance General. Odoo passes the selected record IDs as `docids`. This means the PDF covers exactly the filtered/selected lines — the same records visible in the list.

- [ ] **Step 1: Create AbstractModel**

```python
from odoo import models


class AccountBalanceSheetReport(models.AbstractModel):
    _name = 'report.account_balance_sheet.account_balance_sheet_document'
    _description = 'Balance Sheet Report'

    def _get_report_values(self, docids, data=None):
        # docids = IDs of account.balance.sheet lines selected in the list view
        # (user must select all filtered records before printing for a complete balance sheet)
        lines = self.env['account.balance.sheet'].browse(docids)

        # Aggregate debit/credit per class per account
        aggregated = {}  # {class: {account_id: {code, name, debit, credit}}}
        for line in lines.sorted(key=lambda l: (l.account_class or '', l.account_code or '')):
            cls = line.account_class or '?'
            acct_id = line.account_id.id
            if cls not in aggregated:
                aggregated[cls] = {}
            if acct_id not in aggregated[cls]:
                aggregated[cls][acct_id] = {
                    'account_code': line.account_code or '',
                    'account_name': line.account_name or '',
                    'debit': 0.0,
                    'credit': 0.0,
                }
            aggregated[cls][acct_id]['debit'] += line.debit
            aggregated[cls][acct_id]['credit'] += line.credit

        # Build structured sections with sign-flipped displayed saldo
        # Activo (class 1): saldo = debit - credit  (positive = asset)
        # Pasivo (class 2): saldo = credit - debit  (positive = liability)
        # Patrimonio (class 3): saldo = credit - debit  (positive = equity)
        class_labels = {'1': 'ACTIVO', '2': 'PASIVO', '3': 'PATRIMONIO'}
        sections = []
        totals = {'1': 0.0, '2': 0.0, '3': 0.0}

        for cls in ['1', '2', '3']:
            accounts = []
            for acct_data in sorted(
                aggregated.get(cls, {}).values(),
                key=lambda x: x['account_code'],
            ):
                raw = acct_data['debit'] - acct_data['credit']
                saldo = raw if cls == '1' else -raw
                accounts.append({
                    'account_code': acct_data['account_code'],
                    'account_name': acct_data['account_name'],
                    'saldo': saldo,
                })
                totals[cls] += saldo

            sections.append({
                'class': cls,
                'label': class_labels[cls],
                'accounts': accounts,
                'total': totals[cls],
            })

        total_pasivo_patrimonio = totals['2'] + totals['3']
        equation_diff = totals['1'] - total_pasivo_patrimonio
        equation_ok = abs(equation_diff) < 0.01

        return {
            'doc_ids': docids,
            'sections': sections,
            'total_pasivo_patrimonio': total_pasivo_patrimonio,
            'equation_diff': equation_diff,
            'equation_ok': equation_ok,
        }
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/report/account_balance_sheet_report.py
git commit -m "feat(account_balance_sheet): add PDF report AbstractModel"
```

---

## Task 8: PDF QWeb template

**Files:**
- Create: `custom-addons/account_balance_sheet/report/account_balance_sheet_template.xml`

- [ ] **Step 1: Create template file**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <template id="account_balance_sheet_document">
        <t t-call="web.html_container">
            <t t-call="web.internal_layout">
            <div class="page">

                <h2 t-esc="_('Balance General')"/>

                <t t-foreach="sections" t-as="section">
                    <h4>
                        <t t-out="section['class']"/>. <t t-out="section['label']"/>
                    </h4>
                    <table class="table table-sm table-bordered">
                        <thead>
                            <tr>
                                <th t-esc="_('Code')"/>
                                <th t-esc="_('Account')"/>
                                <th class="text-end" t-esc="_('Balance')"/>
                            </tr>
                        </thead>
                        <tbody>
                            <t t-foreach="section['accounts']" t-as="acct">
                                <tr>
                                    <td><t t-out="acct['account_code']"/></td>
                                    <td><t t-out="acct['account_name']"/></td>
                                    <td class="text-end">
                                        <t t-out="'%.2f' % acct['saldo']"/>
                                    </td>
                                </tr>
                            </t>
                        </tbody>
                        <tfoot>
                            <tr>
                                <td colspan="2">
                                    <strong>
                                        Total <t t-out="section['label'].title()"/>
                                    </strong>
                                </td>
                                <td class="text-end">
                                    <strong>
                                        <t t-out="'%.2f' % section['total']"/>
                                    </strong>
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </t>

                <!-- Equation check -->
                <table class="table table-sm mt-4">
                    <tbody>
                        <tr>
                            <td>
                                <strong t-esc="_('Total Pasivo + Patrimonio')"/>
                            </td>
                            <td class="text-end">
                                <strong>
                                    <t t-out="'%.2f' % total_pasivo_patrimonio"/>
                                </strong>
                            </td>
                        </tr>
                        <tr>
                            <td colspan="2">
                                <t t-if="equation_ok">
                                    <strong class="text-success">
                                        ✓ Activo = Pasivo + Patrimonio
                                    </strong>
                                </t>
                                <t t-else="">
                                    <strong class="text-danger">
                                        ✗ Activo ≠ Pasivo + Patrimonio
                                        (diferencia: <t t-out="'%.2f' % equation_diff"/>)
                                    </strong>
                                </t>
                            </td>
                        </tr>
                    </tbody>
                </table>

            </div>
            </t>
        </t>
    </template>

    <record id="action_report_account_balance_sheet" model="ir.actions.report">
        <field name="name">Balance General</field>
        <field name="model">account.balance.sheet</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">account_balance_sheet.account_balance_sheet_document</field>
        <field name="report_file">account_balance_sheet.account_balance_sheet_document</field>
        <field name="binding_model_id" ref="model_account_balance_sheet"/>
        <field name="binding_type">report</field>
    </record>

</odoo>
```

- [ ] **Step 2: Commit**

```bash
git add custom-addons/account_balance_sheet/report/account_balance_sheet_template.xml
git commit -m "feat(account_balance_sheet): add QWeb PDF template and report action"
```

---

## Task 9: i18n

**Files:**
- Create: `custom-addons/account_balance_sheet/i18n/es.po`
- Create: `custom-addons/account_balance_sheet/i18n/es_419.po`

- [ ] **Step 1: Create `i18n/es.po`**

```po
# Spanish translation for account_balance_sheet
# Copyright (C) 2026 Manuel Caro
# This file is distributed under the same license as the account_balance_sheet module.
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Balance Sheet Report 18.0\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2026-03-17 00:00+0000\n"
"PO-Revision-Date: 2026-03-17 00:00+0000\n"
"Last-Translator: Manuel Caro\n"
"Language-Team: Spanish\n"
"Language: es\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#. module: account_balance_sheet
#: model:ir.model,name:account_balance_sheet.model_account_balance_sheet
msgid "Balance Sheet"
msgstr "Balance General"

#. module: account_balance_sheet
#: model:ir.actions.act_window,name:account_balance_sheet.action_account_balance_sheet
#: model:ir.actions.report,name:account_balance_sheet.action_report_account_balance_sheet
#: model:ir.ui.menu,name:account_balance_sheet.menu_account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_pivot
msgid "Balance General"
msgstr "Balance General"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__date
msgid "Date"
msgstr "Fecha"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_id
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_name
msgid "Account"
msgstr "Cuenta"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_code
msgid "Code"
msgstr "Código"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_class
msgid "Class"
msgstr "Clase"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__move_id
msgid "Journal Entry"
msgstr "Asiento Contable"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__move_name
msgid "Reference"
msgstr "Referencia"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__partner_id
msgid "Partner"
msgstr "Contacto"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__debit
msgid "Debit"
msgstr "Debe"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__credit
msgid "Credit"
msgstr "Haber"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__balance
msgid "Balance"
msgstr "Saldo"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__company_id
msgid "Company"
msgstr "Compañía"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__currency_id
msgid "Currency"
msgstr "Moneda"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Debit"
msgstr "Total Debe"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Credit"
msgstr "Total Haber"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Balance"
msgstr "Total Saldo"

#. module: account_balance_sheet
#: report:account_balance_sheet.account_balance_sheet_document
msgid "Balance General"
msgstr "Balance General"

#. module: account_balance_sheet
#: report:account_balance_sheet.account_balance_sheet_document
msgid "Total Pasivo + Patrimonio"
msgstr "Total Pasivo + Patrimonio"
```

- [ ] **Step 2: Create `i18n/es_419.po`** (identical content, different header)

```po
# Spanish (Latin America) translation for account_balance_sheet
# Copyright (C) 2026 Manuel Caro
# This file is distributed under the same license as the account_balance_sheet module.
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Balance Sheet Report 18.0\n"
"Report-Msgid-Bugs-To: \n"
"POT-Creation-Date: 2026-03-17 00:00+0000\n"
"PO-Revision-Date: 2026-03-17 00:00+0000\n"
"Last-Translator: Manuel Caro\n"
"Language-Team: Spanish (Latin America)\n"
"Language: es_419\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#. module: account_balance_sheet
#: model:ir.model,name:account_balance_sheet.model_account_balance_sheet
msgid "Balance Sheet"
msgstr "Balance General"

#. module: account_balance_sheet
#: model:ir.actions.act_window,name:account_balance_sheet.action_account_balance_sheet
#: model:ir.actions.report,name:account_balance_sheet.action_report_account_balance_sheet
#: model:ir.ui.menu,name:account_balance_sheet.menu_account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_pivot
msgid "Balance General"
msgstr "Balance General"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__date
msgid "Date"
msgstr "Fecha"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_id
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_name
msgid "Account"
msgstr "Cuenta"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_code
msgid "Code"
msgstr "Código"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__account_class
msgid "Class"
msgstr "Clase"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__move_id
msgid "Journal Entry"
msgstr "Asiento Contable"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__move_name
msgid "Reference"
msgstr "Referencia"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__partner_id
msgid "Partner"
msgstr "Contacto"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__debit
msgid "Debit"
msgstr "Debe"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__credit
msgid "Credit"
msgstr "Haber"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__balance
msgid "Balance"
msgstr "Saldo"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__company_id
msgid "Company"
msgstr "Compañía"

#. module: account_balance_sheet
#: model:ir.model.fields,field_description:account_balance_sheet.field_account_balance_sheet__currency_id
msgid "Currency"
msgstr "Moneda"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Debit"
msgstr "Total Debe"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Credit"
msgstr "Total Haber"

#. module: account_balance_sheet
#: model:ir.ui.view,arch_db:account_balance_sheet.account_balance_sheet_view_list
msgid "Total Balance"
msgstr "Total Saldo"

#. module: account_balance_sheet
#: report:account_balance_sheet.account_balance_sheet_document
msgid "Balance General"
msgstr "Balance General"

#. module: account_balance_sheet
#: report:account_balance_sheet.account_balance_sheet_document
msgid "Total Pasivo + Patrimonio"
msgstr "Total Pasivo + Patrimonio"
```

- [ ] **Step 3: Commit**

```bash
git add custom-addons/account_balance_sheet/i18n/
git commit -m "feat(account_balance_sheet): add Spanish (es/es_419) translations"
```

---

## Task 10: Final update and full test run

- [ ] **Step 1: Update module (picks up report model + template + i18n)**

```bash
docker compose run --rm odoo python /odoo/odoo-bin \
  -d odoo \
  -c /etc/odoo/odoo.conf \
  -u account_balance_sheet \
  --test-tags account_balance_sheet \
  --stop-after-init
```

Expected: all tests pass. No `ERROR` lines in output.

- [ ] **Step 2: Smoke-test the PDF from the UI**

1. Open http://localhost:8069 → Accounting → Reporting → Balance General
2. Select all records with the header checkbox
3. Action menu → Print → Balance General
4. Confirm a PDF downloads with ACTIVO / PASIVO / PATRIMONIO sections and the equation check

- [ ] **Step 3: Verify Excel export works**

Click the export icon (↓) in the list view header. Confirm `.xlsx` downloads with all columns.

- [ ] **Step 4: Verify Spanish labels**

Set user language to Spanish (Settings → Users → your user → Language = Spanish / Español). Reload Accounting → Reporting. Confirm menu shows "Balance General" and column headers show "Clase, Código, Cuenta, Referencia, Contacto, Debe, Haber, Saldo".

- [ ] **Step 5: Final commit**

```bash
git add custom-addons/account_balance_sheet/
git commit -m "feat(account_balance_sheet): complete Balance Sheet report module"
```
