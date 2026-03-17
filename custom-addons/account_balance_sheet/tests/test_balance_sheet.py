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
        self.assertEqual(
            classes, {'1', '2', '3'},
            f"Expected all three classes {{1, 2, 3}}, got: {classes}",
        )
