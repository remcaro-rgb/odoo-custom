import datetime
from dateutil.relativedelta import relativedelta

from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged('club_core', 'post_install', '-at_install')
class TestClubMembership(TransactionCase):

    def setUp(self):
        super().setUp()
        self.product = self.env['product.product'].create({
            'name': 'Annual Membership', 'type': 'service', 'list_price': 1200.0
        })
        self.late_fee_product = self.env['product.product'].create({
            'name': 'Late Fee', 'type': 'service', 'list_price': 50.0
        })
        self.plan_annual = self.env['club.membership.plan'].create({
            'name': 'Test Annual Plan',
            'fee': 1200.0,
            'billing_period': 'annual',
            'grace_period_days': 15,
            'late_fee_amount': 50.0,
            'product_id': self.product.id,
            'late_fee_product_id': self.late_fee_product.id,
        })
        self.plan_monthly = self.env['club.membership.plan'].create({
            'name': 'Test Monthly Plan',
            'fee': 120.0,
            'billing_period': 'monthly',
            'grace_period_days': 7,
            'late_fee_amount': 20.0,
            'product_id': self.product.id,
            'late_fee_product_id': self.late_fee_product.id,
        })
        self.affiliate = self.env['club.affiliate'].create({
            'name': 'Test Member', 'membership_type': 'individual'
        })

    def test_end_date_annual(self):
        """Annual membership end_date = start_date + 1 year."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': datetime.date(2026, 1, 1),
        })
        self.assertEqual(
            membership.end_date,
            datetime.date(2027, 1, 1),
            'Annual end_date should be start_date + 1 year.'
        )

    def test_end_date_monthly(self):
        """Monthly membership end_date = start_date + 1 month."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_monthly.id,
            'start_date': datetime.date(2026, 1, 15),
        })
        self.assertEqual(
            membership.end_date,
            datetime.date(2026, 2, 15),
            'Monthly end_date should be start_date + 1 month.'
        )

    def test_end_date_recomputes_on_plan_change(self):
        """end_date recomputes when plan changes."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': datetime.date(2026, 1, 1),
        })
        self.assertEqual(membership.end_date, datetime.date(2027, 1, 1))
        membership.plan_id = self.plan_monthly
        self.assertEqual(
            membership.end_date,
            datetime.date(2026, 2, 1),
            'end_date should recompute after plan change to monthly.'
        )

    def test_action_activate_creates_invoice(self):
        """Activating a membership creates one invoice and links it."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': datetime.date(2026, 1, 1),
        })
        self.assertEqual(membership.status, 'draft')
        self.assertEqual(membership.invoice_count, 0)

        membership.action_activate()

        self.assertEqual(membership.status, 'active')
        self.assertEqual(membership.invoice_count, 1)
        invoice = membership.invoice_ids[0]
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.affiliate.partner_id)
        self.assertAlmostEqual(invoice.amount_untaxed, 1200.0)

    def test_cannot_activate_non_draft(self):
        """Cannot activate a membership that is not in draft status."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': datetime.date(2026, 1, 1),
            'status': 'active',
        })
        with self.assertRaises(UserError):
            membership.action_activate()

    def test_late_fee_creates_new_invoice(self):
        """Late fee generates a NEW invoice, does not modify existing one."""
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': datetime.date(2026, 1, 1),
            'status': 'active',
        })
        membership._generate_membership_invoice()
        self.assertEqual(membership.invoice_count, 1)

        membership._generate_late_fee_invoice()
        self.assertEqual(membership.invoice_count, 2)

        invoices = membership.invoice_ids
        amounts = sorted(inv.amount_untaxed for inv in invoices)
        self.assertEqual(amounts, [50.0, 1200.0])

    def test_generate_late_fee_skipped_without_product(self):
        """Late fee is not generated if late_fee_product_id is not set."""
        plan_no_late_fee = self.env['club.membership.plan'].create({
            'name': 'No Late Fee Plan',
            'fee': 500.0,
            'billing_period': 'annual',
            'product_id': self.product.id,
            # late_fee_product_id intentionally omitted
        })
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': plan_no_late_fee.id,
            'start_date': datetime.date(2026, 1, 1),
        })
        result = membership._generate_late_fee_invoice()
        self.assertFalse(result, 'Should return False when no late fee product.')
        self.assertEqual(membership.invoice_count, 0)

    def test_cron_check_renewals_creates_invoice(self):
        """Renewal cron creates invoice for membership expiring within 7 days."""
        today = datetime.date.today()
        expiring_soon = today + datetime.timedelta(days=3)
        # Use end_date - billing_period as the start to land end_date near today
        start = expiring_soon - datetime.timedelta(days=365)
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': start,
            'status': 'active',
        })
        # end_date = start + 1 year ≈ today + 3 days → within 7-day renewal window
        self.assertTrue(membership.end_date <= today + datetime.timedelta(days=7))
        self.assertEqual(membership.invoice_count, 0)

        self.env['club.membership']._cron_check_renewals()

        self.assertEqual(membership.invoice_count, 1)
        invoice = membership.invoice_ids[0]
        self.assertEqual(invoice.move_type, 'out_invoice')

    def test_cron_check_renewals_no_duplicate(self):
        """Renewal cron does not create a second invoice if already created today."""
        today = datetime.date.today()
        expiring_soon = today + datetime.timedelta(days=3)
        start = expiring_soon - datetime.timedelta(days=365)
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': start,
            'status': 'active',
        })
        # Simulate an invoice already generated today
        membership._generate_membership_invoice()
        self.assertEqual(membership.invoice_count, 1)

        # Run cron — should not create a second invoice
        self.env['club.membership']._cron_check_renewals()
        self.assertEqual(membership.invoice_count, 1)

    def test_cron_apply_late_fees_suspends_membership(self):
        """Late fee cron suspends membership with unpaid invoice past grace period."""
        past_date = datetime.date(2025, 1, 1)
        membership = self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan_annual.id,
            'start_date': past_date,
            'status': 'active',
        })
        # Create a posted (unpaid) invoice
        invoice = membership._generate_membership_invoice()
        invoice.action_post()

        # end_date is 2026-01-01, grace is 15 days → past grace today (2026-03-12)
        self.assertTrue(datetime.date.today() > membership.end_date)

        self.env['club.membership']._cron_apply_late_fees()

        self.assertEqual(membership.status, 'suspended')
        self.assertEqual(membership.invoice_count, 2)  # original + late fee
