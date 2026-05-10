from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('saas_tenant_gate', '-at_install', 'post_install')
class TestSeatCap(TransactionCase):

    def setUp(self):
        super().setUp()
        self.IrConfig = self.env['ir.config_parameter'].sudo()
        self.Users = self.env['res.users']

    def _set_cap(self, cap):
        self.IrConfig.set_param('saas.seat_cap', str(cap))

    def _count_internal_active(self):
        return self.Users.search_count([
            ('share', '=', False),
            ('active', '=', True),
        ])

    def _make_user_vals(self, login, share=False):
        return {
            'name': login,
            'login': login,
            'email': login,
            'share': share,
        }

    def test_unlimited_cap_allows_creation(self):
        """A seat cap of 0 means unlimited; creation must succeed."""
        self._set_cap(0)
        user = self.Users.create(self._make_user_vals('saas_test_unlimited@example.com'))
        self.assertTrue(user.id)

    def test_cap_exceeded_raises(self):
        """Cap below current count + 1 must raise UserError on create."""
        current = self._count_internal_active()
        self._set_cap(current)  # exactly at cap; any internal create now fails
        with self.assertRaises(UserError):
            self.Users.create(self._make_user_vals('saas_test_over@example.com'))

    def test_cap_at_boundary_allows_one_more(self):
        """Cap = current + 1 must allow exactly one new internal user."""
        current = self._count_internal_active()
        self._set_cap(current + 1)
        user = self.Users.create(self._make_user_vals('saas_test_boundary@example.com'))
        self.assertTrue(user.id)
        # A second create now would exceed; verify.
        with self.assertRaises(UserError):
            self.Users.create(self._make_user_vals('saas_test_boundary2@example.com'))

    def test_portal_users_do_not_count(self):
        """share=True users (portal) are out of scope for seat cap."""
        current = self._count_internal_active()
        self._set_cap(current)  # at cap for internal
        portal = self.Users.create(self._make_user_vals('saas_test_portal@example.com', share=True))
        self.assertTrue(portal.id)
        # Internal still capped.
        with self.assertRaises(UserError):
            self.Users.create(self._make_user_vals('saas_test_internal_after_portal@example.com'))

    def test_inactive_users_do_not_count(self):
        """Deactivated users free up a seat for the cap math."""
        current = self._count_internal_active()
        self._set_cap(current + 1)
        user_a = self.Users.create(self._make_user_vals('saas_test_inactive_a@example.com'))
        # Now at cap. Deactivate user_a → another creation should fit.
        user_a.active = False
        user_b = self.Users.create(self._make_user_vals('saas_test_inactive_b@example.com'))
        self.assertTrue(user_b.id)

    def test_rejection_writes_audit_entry(self):
        """A blocked create must leave an ir.logging row tagged saas_tenant_gate."""
        current = self._count_internal_active()
        self._set_cap(current)
        Logging = self.env['ir.logging'].sudo()
        before = Logging.search_count([('name', '=', 'saas_tenant_gate')])
        with self.assertRaises(UserError):
            self.Users.create(self._make_user_vals('saas_test_audit@example.com'))
        after = Logging.search_count([('name', '=', 'saas_tenant_gate')])
        self.assertEqual(after, before + 1)
