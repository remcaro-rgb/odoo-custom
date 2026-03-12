from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import AccessError


@tagged('club_core', 'post_install', '-at_install')
class TestClubAccessRights(TransactionCase):

    def setUp(self):
        super().setUp()
        # Create a portal user linked to an affiliate
        self.portal_partner = self.env['res.partner'].create({'name': 'Portal User'})
        self.portal_user = self.env['res.users'].create({
            'name': 'Portal User',
            'login': 'portaluser@test.com',
            'partner_id': self.portal_partner.id,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_portal').id,
                self.env.ref('club_core.group_club_member').id,
            ])],
        })
        # Create the affiliate for this portal user
        self.own_affiliate = self.env['club.affiliate'].create({
            'partner_id': self.portal_partner.id,
            'membership_type': 'individual',
        })
        # Create a different affiliate (should NOT be visible to portal user)
        self.other_affiliate = self.env['club.affiliate'].create({
            'name': 'Other Person',
            'membership_type': 'individual',
        })

    def test_portal_user_sees_own_affiliate(self):
        """Portal user can read their own affiliate record."""
        affiliates = self.env['club.affiliate'].with_user(self.portal_user).search([])
        self.assertIn(
            self.own_affiliate,
            affiliates,
            'Portal user should see their own affiliate.'
        )

    def test_portal_user_cannot_see_other_affiliate(self):
        """Portal user cannot see other affiliates due to ir.rule."""
        affiliates = self.env['club.affiliate'].with_user(self.portal_user).search([])
        self.assertNotIn(
            self.other_affiliate,
            affiliates,
            'Portal user should NOT see other affiliates.'
        )

    def test_portal_user_cannot_write_affiliate(self):
        """Portal user cannot write to affiliate records."""
        with self.assertRaises(AccessError):
            self.own_affiliate.with_user(self.portal_user).write({
                'email': 'hacked@test.com'
            })

    def test_staff_user_sees_all_affiliates(self):
        """Staff user can read all affiliate records."""
        staff_user = self.env['res.users'].create({
            'name': 'Staff',
            'login': 'staff@test.com',
            'groups_id': [(6, 0, [
                self.env.ref('club_core.group_club_staff').id
            ])],
        })
        affiliates = self.env['club.affiliate'].with_user(staff_user).search([])
        self.assertIn(self.own_affiliate, affiliates)
        self.assertIn(self.other_affiliate, affiliates)
