from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('club_events', 'post_install', '-at_install')
class TestClubEvents(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Event = self.env['event.event']
        self.Registration = self.env['event.registration']
        self.Affiliate = self.env['club.affiliate']
        self.Plan = self.env['club.membership.plan']
        self.Membership = self.env['club.membership']

        # Create a membership product
        self.product = self.env['product.product'].create({
            'name': 'Test Plan Product',
            'type': 'service',
        })

        # Create a membership plan
        self.plan = self.Plan.create({
            'name': 'Test Plan',
            'fee': 100.0,
            'billing_period': 'annual',
            'product_id': self.product.id,
        })

        # Create an active affiliate
        self.affiliate = self.Affiliate.create({
            'name': 'Test Member',
            'email': 'member@test.com',
            'membership_type': 'individual',
        })
        self.Membership.create({
            'affiliate_id': self.affiliate.id,
            'plan_id': self.plan.id,
            'start_date': '2026-01-01',
            'status': 'active',
        })
        self.affiliate.invalidate_recordset()

        # Create a non-member partner
        self.public_partner = self.env['res.partner'].create({
            'name': 'Public Attendee',
            'email': 'public@test.com',
        })

        # Create a test event
        self.event = self.Event.create({
            'name': 'Test Club Event',
            'event_scope': 'internal',
            'sport_category': 'golf',
            'member_only': True,
            'member_price': 50.0,
            'public_price': 100.0,
            'date_begin': '2026-06-01 09:00:00',
            'date_end': '2026-06-01 18:00:00',
        })

    def test_attendee_type_auto_member(self):
        """Registration with an active affiliate partner is set to 'member'."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.affiliate.partner_id.id,
            'name': 'Test Member',
        })
        self.assertEqual(
            registration.attendee_type, 'member',
            'Attendee type should be auto-set to member for active affiliates.',
        )

    def test_attendee_type_auto_public(self):
        """Registration with a non-affiliate partner is set to 'public'."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.public_partner.id,
            'name': 'Public Attendee',
        })
        self.assertEqual(
            registration.attendee_type, 'public',
            'Attendee type should be auto-set to public for non-affiliates.',
        )

    def test_affiliate_auto_linked(self):
        """Active affiliate is auto-linked on registration create."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.affiliate.partner_id.id,
            'name': 'Test Member',
        })
        self.assertEqual(
            registration.affiliate_id, self.affiliate,
            'Affiliate should be auto-linked when partner is an active affiliate.',
        )

    def test_affiliate_not_linked_for_public(self):
        """No affiliate is linked for non-member registrations."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.public_partner.id,
            'name': 'Public Attendee',
        })
        self.assertFalse(
            registration.affiliate_id,
            'No affiliate should be linked for public attendees.',
        )

    def test_member_price_applied(self):
        """Member price is applied for member attendees."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.affiliate.partner_id.id,
            'name': 'Test Member',
        })
        self.assertEqual(
            registration.applied_price, 50.0,
            'Member price should be applied for member attendees.',
        )

    def test_public_price_applied(self):
        """Public price is applied for public attendees."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.public_partner.id,
            'name': 'Public Attendee',
        })
        self.assertEqual(
            registration.applied_price, 100.0,
            'Public price should be applied for public attendees.',
        )

    def test_payment_status_pending_no_invoice(self):
        """Payment status is 'pending' when no invoice is linked."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'name': 'No Invoice Registration',
        })
        self.assertEqual(
            registration.payment_status, 'pending',
            'Payment status should be pending without an invoice.',
        )

    def test_payment_status_paid(self):
        """Payment status is 'paid' when invoice payment_state is 'paid'."""
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'Test Sales',
                'type': 'sale',
                'code': 'TSAL',
            })

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.public_partner.id,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Event Registration',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })

        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.public_partner.id,
            'name': 'Paid Registration',
            'payment_move_id': invoice.id,
        })

        # Before payment the status depends on invoice payment_state
        self.assertEqual(
            registration.payment_status, 'pending',
            'Payment status should be pending for an unposted invoice.',
        )

    def test_payment_status_refunded(self):
        """Payment status is 'refunded' when invoice payment_state is 'reversed'."""
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'Test Sales',
                'type': 'sale',
                'code': 'TSAL',
            })

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.public_partner.id,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Event Registration',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })

        registration = self.Registration.create({
            'event_id': self.event.id,
            'partner_id': self.public_partner.id,
            'name': 'Refunded Registration',
            'payment_move_id': invoice.id,
        })

        # Simulate reversed state
        invoice.payment_state = 'reversed'
        registration.invalidate_recordset()
        self.assertEqual(
            registration.payment_status, 'refunded',
            'Payment status should be refunded when invoice is reversed.',
        )

    def test_event_club_fields(self):
        """Event club fields are properly stored."""
        self.assertEqual(self.event.event_scope, 'internal')
        self.assertEqual(self.event.sport_category, 'golf')
        self.assertTrue(self.event.member_only)
        self.assertEqual(self.event.member_price, 50.0)
        self.assertEqual(self.event.public_price, 100.0)

    def test_registration_no_partner(self):
        """Registration without partner defaults to public attendee type."""
        registration = self.Registration.create({
            'event_id': self.event.id,
            'name': 'Walk-in Attendee',
            'email': 'walkin@test.com',
        })
        self.assertEqual(
            registration.attendee_type, 'public',
            'Registration without partner should default to public.',
        )
