from odoo.tests import tagged, TransactionCase


@tagged('club_pos', 'post_install', '-at_install')
class TestClubPos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Payment method fields
        cls.PaymentMethod = cls.env['pos.payment.method']

        # Create affiliate
        test_product = cls.env['product.product'].create({
            'name': 'Test Plan Product POS', 'type': 'service',
        })
        cls.plan = cls.env['club.membership.plan'].create({
            'name': 'Test POS Plan',
            'billing_period': 'monthly',
            'fee': 100.0,
            'product_id': test_product.id,
        })
        cls.affiliate = cls.env['club.affiliate'].create({
            'name': 'POS Test Affiliate',
            'membership_type': 'individual',
        })
        cls.env['club.membership'].create({
            'affiliate_id': cls.affiliate.id,
            'plan_id': cls.plan.id,
            'status': 'active',
            'start_date': '2025-01-01',
        })
        # Non-affiliate partner
        cls.partner_no_affiliate = cls.env['res.partner'].create({
            'name': 'Not An Affiliate POS',
        })

    def test_payment_method_cargo_socio_fields(self):
        """Payment method should have is_cargo_socio and account fields."""
        pm = self.PaymentMethod.new({
            'name': 'Test Cargo',
            'is_cargo_socio': True,
        })
        self.assertTrue(pm.is_cargo_socio)

    def test_partner_is_club_affiliate(self):
        """Partner linked to an affiliate should have is_club_affiliate=True."""
        partner = self.affiliate.partner_id
        partner._compute_is_club_affiliate()
        self.assertTrue(partner.is_club_affiliate)
        self.assertEqual(partner.club_affiliate_number, self.affiliate.affiliate_number)
        self.assertEqual(partner.club_membership_status, 'active')

    def test_partner_not_affiliate(self):
        """Partner not linked to an affiliate should have is_club_affiliate=False."""
        self.partner_no_affiliate._compute_is_club_affiliate()
        self.assertFalse(self.partner_no_affiliate.is_club_affiliate)

    def test_pos_data_fields_include_affiliate(self):
        """POS data fields should include affiliate info."""
        fields_list = self.env['res.partner']._load_pos_data_fields(False)
        self.assertIn('is_club_affiliate', fields_list)
        self.assertIn('club_affiliate_number', fields_list)
        self.assertIn('club_membership_status', fields_list)
