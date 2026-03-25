from odoo import fields
from odoo.tests import tagged, TransactionCase


@tagged('club_affiliate_billing', 'post_install', '-at_install')
class TestAffiliateBilling(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.BillingRun = cls.env['club.affiliate.billing.run']
        cls.BillingInvoice = cls.env['club.affiliate.billing.invoice']
        cls.BillingLine = cls.env['club.affiliate.billing.line']

        test_product = cls.env['product.product'].create({
            'name': 'Billing Test Product', 'type': 'service',
        })
        cls.plan = cls.env['club.membership.plan'].create({
            'name': 'Billing Test Plan',
            'billing_period': 'monthly',
            'fee': 100.0,
            'product_id': test_product.id,
        })
        cls.affiliate = cls.env['club.affiliate'].create({
            'name': 'Billing Test Affiliate',
            'membership_type': 'individual',
        })
        cls.env['club.membership'].create({
            'affiliate_id': cls.affiliate.id,
            'plan_id': cls.plan.id,
            'status': 'active',
            'start_date': '2025-01-01',
        })

    def test_01_auto_sequence(self):
        """Billing run should get auto-sequence."""
        today = fields.Date.today()
        run = self.BillingRun.create({
            'period_start': today.replace(day=1),
            'period_end': today,
        })
        self.assertTrue(run.name)
        self.assertIn('BILL', run.name)

    def test_02_status_transitions(self):
        """Cancel and reset should work."""
        today = fields.Date.today()
        run = self.BillingRun.create({
            'period_start': today.replace(day=1),
            'period_end': today,
        })
        self.assertEqual(run.status, 'draft')
        run.action_cancel()
        self.assertEqual(run.status, 'cancelled')
        run.action_draft()
        self.assertEqual(run.status, 'draft')

    def test_03_billing_invoice_total(self):
        """Billing invoice total should sum lines."""
        today = fields.Date.today()
        run = self.BillingRun.create({
            'period_start': today.replace(day=1),
            'period_end': today,
        })
        inv = self.BillingInvoice.create({
            'billing_run_id': run.id,
            'affiliate_id': self.affiliate.id,
        })
        self.BillingLine.create({
            'billing_invoice_id': inv.id,
            'amount': 50.0,
            'description': 'Line 1',
        })
        self.BillingLine.create({
            'billing_invoice_id': inv.id,
            'amount': 75.0,
            'description': 'Line 2',
        })
        inv.invalidate_recordset()
        self.assertEqual(inv.total_amount, 125.0)

    def test_04_run_total(self):
        """Run total should sum billing invoices."""
        today = fields.Date.today()
        run = self.BillingRun.create({
            'period_start': today.replace(day=1),
            'period_end': today,
        })
        inv = self.BillingInvoice.create({
            'billing_run_id': run.id,
            'affiliate_id': self.affiliate.id,
        })
        self.BillingLine.create({
            'billing_invoice_id': inv.id,
            'amount': 200.0,
            'description': 'Charge',
        })
        run.invalidate_recordset()
        self.assertGreater(run.total_amount, 0)
