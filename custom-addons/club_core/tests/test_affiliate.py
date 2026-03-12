from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('club_core', 'post_install', '-at_install')
class TestClubAffiliate(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Affiliate = self.env['club.affiliate']

    def test_affiliate_number_auto_assigned(self):
        """Affiliate number is auto-assigned from sequence on creation."""
        affiliate = self.Affiliate.create({
            'name': 'Test Affiliate',
            'membership_type': 'individual',
        })
        self.assertTrue(
            affiliate.affiliate_number,
            'Affiliate number should be auto-assigned.'
        )
        self.assertTrue(
            affiliate.affiliate_number.startswith('AFF'),
            'Affiliate number should start with AFF prefix.'
        )

    def test_affiliate_number_unique(self):
        """Each affiliate gets a unique affiliate number."""
        a1 = self.Affiliate.create({'name': 'A1', 'membership_type': 'individual'})
        a2 = self.Affiliate.create({'name': 'A2', 'membership_type': 'individual'})
        self.assertNotEqual(
            a1.affiliate_number,
            a2.affiliate_number,
            'Two affiliates must have different affiliate numbers.'
        )

    def test_affiliate_inherits_partner_fields(self):
        """Affiliate transparently exposes res.partner fields via _inherits."""
        affiliate = self.Affiliate.create({
            'name': 'Juan Test',
            'email': 'juan@test.com',
            'membership_type': 'individual',
        })
        self.assertEqual(affiliate.name, 'Juan Test')
        self.assertEqual(affiliate.email, 'juan@test.com')
        # Verify a separate partner was created
        self.assertTrue(affiliate.partner_id)
        self.assertEqual(affiliate.partner_id.name, 'Juan Test')

    def test_membership_status_none_without_memberships(self):
        """Affiliate with no memberships has status 'none'."""
        affiliate = self.Affiliate.create({
            'name': 'No Membership',
            'membership_type': 'individual',
        })
        self.assertEqual(affiliate.membership_status, 'none')

    def test_membership_status_active_with_active_membership(self):
        """Affiliate with active membership shows status 'active'."""
        product = self.env['product.product'].create({
            'name': 'Test Plan Product', 'type': 'service'
        })
        plan = self.env['club.membership.plan'].create({
            'name': 'Test Plan',
            'fee': 100.0,
            'billing_period': 'annual',
            'product_id': product.id,
        })
        affiliate = self.Affiliate.create({
            'name': 'Active Member',
            'membership_type': 'individual',
        })
        self.env['club.membership'].create({
            'affiliate_id': affiliate.id,
            'plan_id': plan.id,
            'start_date': '2026-01-01',
            'status': 'active',
        })
        affiliate.invalidate_recordset()
        self.assertEqual(affiliate.membership_status, 'active')

    def test_membership_status_suspended(self):
        """Affiliate with only suspended membership shows 'suspended'."""
        product = self.env['product.product'].create({
            'name': 'SP', 'type': 'service'
        })
        plan = self.env['club.membership.plan'].create({
            'name': 'SP Plan', 'fee': 100.0, 'billing_period': 'annual',
            'product_id': product.id,
        })
        affiliate = self.Affiliate.create({
            'name': 'Suspended', 'membership_type': 'individual'
        })
        self.env['club.membership'].create({
            'affiliate_id': affiliate.id,
            'plan_id': plan.id,
            'start_date': '2025-01-01',
            'status': 'suspended',
        })
        affiliate.invalidate_recordset()
        self.assertEqual(affiliate.membership_status, 'suspended')
