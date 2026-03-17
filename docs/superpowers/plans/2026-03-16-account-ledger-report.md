# Account Ledger Report — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Odoo 18 module (`account_ledger_report`) that shows all posted journal entry lines grouped/filtered by account, partner, date, and invoice — with list view, pivot, PDF, and Excel export.

**Architecture:** SQL-backed readonly model (`_auto = False`) using `_table_query` over `account_move_line` joined with `account_move`, `account_account`, and `res_currency`. Views are pure XML. PDF via QWeb template. Excel via native Odoo list export.

**Tech Stack:** Odoo 18, Python (model only), XML (views + QWeb), PostgreSQL (SQL view)

---

## File Map

| File | Responsibility |
|------|---------------|
| `__manifest__.py` | Module metadata and data file registry |
| `__init__.py` | Package init (imports models) |
| `models/__init__.py` | Models package init |
| `models/account_ledger_report.py` | `account.ledger.report` — SQL view model |
| `views/account_ledger_report_views.xml` | List, pivot, search views + action + menu |
| `report/account_ledger_report_template.xml` | QWeb PDF template + `ir.actions.report` |
| `security/ir.model.access.csv` | Read ACL for accounting groups |
| `tests/__init__.py` | Tests package init |
| `tests/test_account_ledger_report.py` | Unit tests for SQL model |

---

## Chunk 1: Module Scaffold + SQL Model

### Task 1: Create module scaffold

**Files:**
- Create: `custom-addons/account_ledger_report/__init__.py`
- Create: `custom-addons/account_ledger_report/__manifest__.py`
- Create: `custom-addons/account_ledger_report/models/__init__.py`
- Create: `custom-addons/account_ledger_report/tests/__init__.py`

- [ ] **Step 1: Create root `__init__.py`**

  File: `custom-addons/account_ledger_report/__init__.py`
  ```python
  from . import models
  ```

- [ ] **Step 2: Create `__manifest__.py`**

  File: `custom-addons/account_ledger_report/__manifest__.py`
  ```python
  {
      'name': 'Account Ledger Report',
      'version': '18.0.1.0.0',
      'summary': 'Live account ledger report with PDF and Excel export',
      'category': 'Accounting',
      'depends': ['account'],
      'data': [
          'security/ir.model.access.csv',
          'views/account_ledger_report_views.xml',
          'report/account_ledger_report_template.xml',
      ],
      'installable': True,
      'auto_install': False,
      'license': 'LGPL-3',
  }
  ```

- [ ] **Step 3: Create `models/__init__.py`**

  File: `custom-addons/account_ledger_report/models/__init__.py`
  ```python
  from . import account_ledger_report
  ```

- [ ] **Step 4: Create `tests/__init__.py`**

  File: `custom-addons/account_ledger_report/tests/__init__.py`
  ```python
  from . import test_account_ledger_report
  ```

- [ ] **Step 5: Commit scaffold**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_ledger_report/
  git commit -m "feat(account_ledger_report): add module scaffold"
  ```

---

### Task 2: SQL model + tests (TDD)

**Files:**
- Create: `custom-addons/account_ledger_report/tests/test_account_ledger_report.py`
- Create: `custom-addons/account_ledger_report/models/account_ledger_report.py`

**Background:** `account.ledger.report` is an `_auto = False` model. Odoo creates a database VIEW (not a table) using the SQL returned by `_table_query`. All fields must be populated directly from the SQL SELECT — `related=` fields do NOT work on `_auto = False` models; values for `account_code` and `move_name` come from JOINs in the SQL.

The SQL joins:
- `account_move_line aml` — the base (id, account_id, partner_id, debit, credit, company_id, parent_state)
- `account_move am` — for `date` and `name` (invoice/entry reference)
- `account_account aa` — for `code`
- `res_company rco` + `res_currency rc` — for `currency_id` (required by Monetary fields)

Filter: `aml.parent_state = 'posted'` — `parent_state` is a stored related field on `account_move_line` (stored in the DB column).

- [ ] **Step 1: Write the failing tests**

  File: `custom-addons/account_ledger_report/tests/test_account_ledger_report.py`
  ```python
  from odoo.tests import tagged
  from odoo.tests.common import TransactionCase


  @tagged('account_ledger_report', 'post_install', '-at_install')
  class TestAccountLedgerReport(TransactionCase):

      @classmethod
      def setUpClass(cls):
          super().setUpClass()
          cls.company = cls.env.ref('base.main_company')
          cls.journal = cls.env['account.journal'].search([
              ('type', '=', 'general'),
              ('company_id', '=', cls.company.id),
          ], limit=1)
          cls.account_receivable = cls.env['account.account'].search([
              ('account_type', '=', 'asset_receivable'),
              ('company_id', '=', cls.company.id),
          ], limit=1)
          cls.account_revenue = cls.env['account.account'].search([
              ('account_type', '=', 'income'),
              ('company_id', '=', cls.company.id),
          ], limit=1)

      def _create_posted_move(self, date, debit_account, credit_account, amount):
          move = self.env['account.move'].create({
              'journal_id': self.journal.id,
              'date': date,
              'line_ids': [
                  (0, 0, {
                      'account_id': debit_account.id,
                      'debit': amount,
                      'credit': 0.0,
                  }),
                  (0, 0, {
                      'account_id': credit_account.id,
                      'debit': 0.0,
                      'credit': amount,
                  }),
              ],
          })
          move.action_post()
          return move

      def test_posted_entries_appear(self):
          """Posted journal entries must appear in the report."""
          move = self._create_posted_move(
              '2026-01-15', self.account_receivable, self.account_revenue, 100.0
          )
          lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
          self.assertEqual(len(lines), 2)
          debit_line = lines.filtered(lambda l: l.debit == 100.0)
          self.assertEqual(len(debit_line), 1)
          self.assertEqual(debit_line.account_id, self.account_receivable)

      def test_draft_entries_excluded(self):
          """Draft entries must NOT appear in the report."""
          move = self.env['account.move'].create({
              'journal_id': self.journal.id,
              'date': '2026-01-15',
              'line_ids': [
                  (0, 0, {
                      'account_id': self.account_receivable.id,
                      'debit': 50.0,
                      'credit': 0.0,
                  }),
                  (0, 0, {
                      'account_id': self.account_revenue.id,
                      'debit': 0.0,
                      'credit': 50.0,
                  }),
              ],
          })
          # deliberately NOT posting the move
          lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
          self.assertEqual(len(lines), 0, "Draft entries must not appear")

      def test_account_code_populated(self):
          """account_code must come from the SQL SELECT (not ORM related)."""
          move = self._create_posted_move(
              '2026-01-15', self.account_receivable, self.account_revenue, 200.0
          )
          lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
          for line in lines:
              self.assertTrue(line.account_code, "account_code must be populated from SQL")

      def test_date_filter(self):
          """Date range filter must work correctly."""
          move = self._create_posted_move(
              '2026-02-15', self.account_receivable, self.account_revenue, 75.0
          )
          lines = self.env['account.ledger.report'].search([
              ('move_id', '=', move.id),
              ('date', '>=', '2026-02-01'),
              ('date', '<=', '2026-02-28'),
          ])
          self.assertEqual(len(lines), 2)

      def test_debit_credit_values(self):
          """Debit and credit values must match the journal entry lines."""
          move = self._create_posted_move(
              '2026-01-20', self.account_receivable, self.account_revenue, 300.0
          )
          lines = self.env['account.ledger.report'].search([('move_id', '=', move.id)])
          total_debit = sum(lines.mapped('debit'))
          total_credit = sum(lines.mapped('credit'))
          self.assertEqual(total_debit, 300.0)
          self.assertEqual(total_credit, 300.0)
  ```

- [ ] **Step 2: Run tests — expect failure (model not yet defined)**

  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo --test-tags account_ledger_report --xmlrpc-port=8072 2>&1 | tail -20
  ```
  Expected: ERROR — module fails to load because `account_ledger_report.py` is missing.

- [ ] **Step 3: Write the SQL model**

  File: `custom-addons/account_ledger_report/models/account_ledger_report.py`
  ```python
  from odoo import fields, models


  class AccountLedgerReport(models.Model):
      _name = 'account.ledger.report'
      _description = 'Account Ledger Report'
      _auto = False
      _order = 'date desc, id desc'

      date = fields.Date(string='Date', readonly=True)
      account_id = fields.Many2one('account.account', string='Account', readonly=True)
      account_code = fields.Char(string='Code', readonly=True)
      move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
      move_name = fields.Char(string='Reference', readonly=True)
      partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
      debit = fields.Monetary(string='Debit', readonly=True)
      credit = fields.Monetary(string='Credit', readonly=True)
      company_id = fields.Many2one('res.company', string='Company', readonly=True)
      currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

      @property
      def _table_query(self):
          return """
              SELECT
                  aml.id              AS id,
                  am.date             AS date,
                  aml.account_id      AS account_id,
                  aa.code             AS account_code,
                  aml.move_id         AS move_id,
                  am.name             AS move_name,
                  aml.partner_id      AS partner_id,
                  aml.debit           AS debit,
                  aml.credit          AS credit,
                  aml.company_id      AS company_id,
                  rc.id               AS currency_id
              FROM account_move_line aml
              JOIN account_move    am  ON am.id  = aml.move_id
              JOIN account_account aa  ON aa.id  = aml.account_id
              JOIN res_company     rco ON rco.id = aml.company_id
              JOIN res_currency    rc  ON rc.id  = rco.currency_id
              WHERE aml.parent_state = 'posted'
          """
  ```

- [ ] **Step 4: Create minimal security file so module installs**

  File: `custom-addons/account_ledger_report/security/ir.model.access.csv`
  ```
  id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
  access_account_ledger_report_readonly,account.ledger.report readonly,model_account_ledger_report,account.group_account_readonly,1,0,0,0
  access_account_ledger_report_user,account.ledger.report user,model_account_ledger_report,account.group_account_user,1,0,0,0
  access_account_ledger_report_manager,account.ledger.report manager,model_account_ledger_report,account.group_account_manager,1,0,0,0
  access_account_ledger_report_system,account.ledger.report system,model_account_ledger_report,base.group_system,1,0,0,0
  ```

  **Note:** The manifest lists `security/ir.model.access.csv` first — it must exist before the model is loaded. Create it now with a placeholder views file to allow installation.

- [ ] **Step 5: Create placeholder views file so manifest loads**

  File: `custom-addons/account_ledger_report/views/account_ledger_report_views.xml`
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>
  </odoo>
  ```

- [ ] **Step 6: Create placeholder report file so manifest loads**

  File: `custom-addons/account_ledger_report/report/account_ledger_report_template.xml`
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>
  </odoo>
  ```

- [ ] **Step 7: Install module and run tests**

  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo -i account_ledger_report --xmlrpc-port=8072 2>&1 | tail -5
  ```
  Expected: `Module account_ledger_report loaded`

  Then run tests:
  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo --test-tags account_ledger_report --xmlrpc-port=8072 2>&1 | grep -E "PASS|FAIL|ERROR|tests"
  ```
  Expected: `5 tests, 0 failures, 0 errors` (all 5 tests pass)

- [ ] **Step 8: Commit model and tests**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_ledger_report/
  git commit -m "feat(account_ledger_report): add SQL model and tests"
  ```

---

## Chunk 2: Views + Security

### Task 3: List, pivot, search views + action + menu

**Files:**
- Modify: `custom-addons/account_ledger_report/views/account_ledger_report_views.xml`

**Background:**
- The list view is read-only (`create="false" edit="false" delete="false"`).
- `currency_id` must be present in the list view (invisible) so Monetary fields render correctly.
- The search view uses two `<field name="partner_id">` entries with different `string` and `domain` attributes — one for Customer and one for Provider. Odoo 18 allows this.
- The `date` filter uses `<filter date="date"/>` which provides period-based selection (This Month, Q1-Q4, This Year). For specific start/end dates, use two `<field name="date">` entries with `filter_domain`.
- Menu parent: `account.menu_finance_reports` — Accounting → Reporting. If this ID does not exist in your Odoo instance, check with: `SELECT id, name FROM ir_ui_menu WHERE name = 'Reporting';` against the running DB.

- [ ] **Step 1: Replace placeholder views file with full content**

  File: `custom-addons/account_ledger_report/views/account_ledger_report_views.xml`
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>

      <!-- List View -->
      <record id="account_ledger_report_view_list" model="ir.ui.view">
          <field name="name">account.ledger.report.list</field>
          <field name="model">account.ledger.report</field>
          <field name="arch" type="xml">
              <list string="Account Ledger"
                    create="false" edit="false" delete="false">
                  <field name="date"/>
                  <field name="account_code" optional="show" string="Code"/>
                  <field name="account_id" string="Account"/>
                  <field name="move_name" string="Reference"/>
                  <field name="partner_id" string="Partner"/>
                  <field name="currency_id" column_invisible="1"/>
                  <field name="debit" sum="Total Debit"/>
                  <field name="credit" sum="Total Credit"/>
              </list>
          </field>
      </record>

      <!-- Pivot View -->
      <record id="account_ledger_report_view_pivot" model="ir.ui.view">
          <field name="name">account.ledger.report.pivot</field>
          <field name="model">account.ledger.report</field>
          <field name="arch" type="xml">
              <pivot string="Account Ledger" disable_linking="True">
                  <field name="account_id" type="row"/>
                  <field name="debit" type="measure"/>
                  <field name="credit" type="measure"/>
              </pivot>
          </field>
      </record>

      <!-- Search View -->
      <record id="account_ledger_report_view_search" model="ir.ui.view">
          <field name="name">account.ledger.report.search</field>
          <field name="model">account.ledger.report</field>
          <field name="arch" type="xml">
              <search string="Account Ledger">
                  <field name="account_id" string="Account"/>
                  <field name="partner_id" string="Customer"
                         domain="[('customer_rank', '>', 0)]"/>
                  <field name="partner_id" string="Provider"
                         domain="[('supplier_rank', '>', 0)]"/>
                  <field name="move_id" string="Invoice"/>
                  <field name="date" string="Start Date"
                         filter_domain="[('date', '&gt;=', self)]"/>
                  <field name="date" string="End Date"
                         filter_domain="[('date', '&lt;=', self)]"/>
                  <separator/>
                  <filter string="Date" name="filter_date" date="date"/>
                  <group expand="0" string="Group By">
                      <filter string="Account" name="group_by_account"
                              context="{'group_by': 'account_id'}"/>
                      <filter string="Partner" name="group_by_partner"
                              context="{'group_by': 'partner_id'}"/>
                      <filter string="Month" name="group_by_month"
                              context="{'group_by': 'date:month'}"/>
                  </group>
              </search>
          </field>
      </record>

      <!-- Action -->
      <record id="action_account_ledger_report" model="ir.actions.act_window">
          <field name="name">Account Ledger</field>
          <field name="res_model">account.ledger.report</field>
          <field name="view_mode">list,pivot</field>
          <field name="search_view_id" ref="account_ledger_report_view_search"/>
      </record>

      <!-- Menu: Accounting → Reporting → Account Ledger -->
      <menuitem id="menu_account_ledger_report"
                name="Account Ledger"
                parent="account.menu_finance_reports"
                action="action_account_ledger_report"
                sequence="100"/>

  </odoo>
  ```

- [ ] **Step 2: Update module (apply view changes)**

  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo -u account_ledger_report --xmlrpc-port=8072 2>&1 | tail -5
  ```
  Expected: `Module account_ledger_report loaded` with no errors.

  If you see `External ID not found: account.menu_finance_reports`, find the correct parent menu ID:
  ```bash
  docker compose exec db psql -U odoo -d odoo -c \
    "SELECT id, complete_name FROM ir_ui_menu WHERE complete_name ILIKE '%accounting%report%';"
  ```
  Update `parent=` in the menuitem accordingly and re-run update.

- [ ] **Step 3: Verify views in browser**

  1. Restart Odoo: `docker compose restart odoo`
  2. Go to **Accounting → Reporting → Account Ledger**
  3. Confirm list view loads with columns: Date, Code, Account, Reference, Partner, Debit, Credit
  4. Switch to Pivot view — confirm rows show accounts with Debit/Credit measures
  5. In search bar, confirm: Account, Customer, Provider, Invoice, Start Date, End Date fields appear as suggestions, and a "Date" period filter exists

- [ ] **Step 4: Commit views**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_ledger_report/views/
  git commit -m "feat(account_ledger_report): add list, pivot, search views and menu"
  ```

---

## Chunk 3: PDF Report + Final Verification

### Task 4: QWeb PDF report

**Files:**
- Modify: `custom-addons/account_ledger_report/report/account_ledger_report_template.xml`

**Background:**
- `ir.actions.report` with `binding_model_id` automatically adds a "Print" option to the Action menu on the list view.
- `binding_type = 'report'` links it to the model so it appears in the Print dropdown.
- The QWeb template receives `docs` — the recordset of selected `account.ledger.report` records.
- Monetary values are formatted with `'%.2f' % value` for simplicity (avoids locale dependency in QWeb).
- The `web.internal_layout` call template provides standard Odoo PDF headers/footers (company logo, page numbers).

- [ ] **Step 1: Replace placeholder report file with full content**

  File: `custom-addons/account_ledger_report/report/account_ledger_report_template.xml`
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>

      <template id="account_ledger_report_document">
          <t t-call="web.internal_layout">
              <div class="page">
                      <h2>Account Ledger</h2>
                      <table class="table table-sm table-bordered">
                          <thead>
                              <tr>
                                  <th>Date</th>
                                  <th>Code</th>
                                  <th>Account</th>
                                  <th>Reference</th>
                                  <th>Partner</th>
                                  <th class="text-end">Debit</th>
                                  <th class="text-end">Credit</th>
                              </tr>
                          </thead>
                          <tbody>
                              <t t-foreach="docs" t-as="line">
                                  <tr>
                                      <td><t t-out="line.date"/></td>
                                      <td><t t-out="line.account_code"/></td>
                                      <td><t t-out="line.account_id.name"/></td>
                                      <td><t t-out="line.move_name"/></td>
                                      <td><t t-out="line.partner_id.name or ''"/></td>
                                      <td class="text-end">
                                          <t t-if="line.debit">
                                              <t t-out="'%.2f' % line.debit"/>
                                          </t>
                                      </td>
                                      <td class="text-end">
                                          <t t-if="line.credit">
                                              <t t-out="'%.2f' % line.credit"/>
                                          </t>
                                      </td>
                                  </tr>
                              </t>
                          </tbody>
                          <tfoot>
                              <tr>
                                  <td colspan="5"><strong>Total</strong></td>
                                  <td class="text-end">
                                      <strong>
                                          <t t-out="'%.2f' % sum(docs.mapped('debit'))"/>
                                      </strong>
                                  </td>
                                  <td class="text-end">
                                      <strong>
                                          <t t-out="'%.2f' % sum(docs.mapped('credit'))"/>
                                      </strong>
                                  </td>
                              </tr>
                          </tfoot>
                      </table>
                  </div>
          </t>
      </template>

      <record id="action_account_ledger_report_pdf" model="ir.actions.report">
          <field name="name">Account Ledger</field>
          <field name="model">account.ledger.report</field>
          <field name="report_type">qweb-pdf</field>
          <field name="report_name">account_ledger_report.account_ledger_report_document</field>
          <field name="report_file">account_ledger_report.account_ledger_report_document</field>
          <field name="binding_model_id" ref="model_account_ledger_report"/>
          <field name="binding_type">report</field>
      </record>

  </odoo>
  ```

- [ ] **Step 2: Update module**

  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo -u account_ledger_report --xmlrpc-port=8072 2>&1 | tail -5
  ```
  Expected: `Module account_ledger_report loaded` with no errors.

- [ ] **Step 3: Restart and verify PDF**

  ```bash
  docker compose restart odoo
  ```

  1. Go to **Accounting → Reporting → Account Ledger**
  2. Select one or more rows (checkbox on left)
  3. Click the **Print** dropdown (printer icon in the action bar) → select **Account Ledger**
  4. Confirm a PDF downloads with: page header, table with Date/Code/Account/Reference/Partner/Debit/Credit columns, totals row at the bottom

- [ ] **Step 4: Verify Excel export**

  1. On the list view, click the **⬇ Export** button (top-left, next to select-all)
  2. Confirm an `.xlsx` file downloads with all visible columns
  3. No code changes needed — this is native Odoo behavior

- [ ] **Step 5: Run full test suite**

  ```bash
  docker compose exec odoo odoo --stop-after-init -c /etc/odoo/odoo.conf \
    -d odoo --test-tags account_ledger_report --xmlrpc-port=8072 2>&1 | grep -E "PASS|FAIL|ERROR|tests"
  ```
  Expected: `5 tests, 0 failures, 0 errors`

- [ ] **Step 6: Commit PDF report**

  ```bash
  cd /Users/manuelcaro/Odoo
  git add custom-addons/account_ledger_report/report/
  git commit -m "feat(account_ledger_report): add QWeb PDF report template"
  ```
