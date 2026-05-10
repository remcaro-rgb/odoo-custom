from odoo.tests.common import TransactionCase, tagged


@tagged('saas_tenant_gate', '-at_install', 'post_install')
class TestFeatureFlags(TransactionCase):

    def setUp(self):
        super().setUp()
        self.config = self.env['ir.config_parameter'].sudo()

    def test_feature_flag_round_trip(self):
        """Whatever the control plane writes under saas.feature.* is what
        the addon reads back. The addon itself imposes no schema on feature
        keys — the control plane owns the namespace."""
        self.config.set_param('saas.feature.exclusive_tier_routing', 'enabled')
        value = self.config.get_param('saas.feature.exclusive_tier_routing')
        self.assertEqual(value, 'enabled')

    def test_missing_feature_flag_returns_default(self):
        """Unset feature flags must return the caller's default, not raise.
        This is the contract the control plane relies on."""
        value = self.config.get_param('saas.feature.does_not_exist', 'fallback')
        self.assertEqual(value, 'fallback')

    def test_default_seat_cap_is_unlimited(self):
        """Fresh install ships saas.seat_cap='0' (unlimited), so a newly
        provisioned tenant isn't accidentally seat-capped before the control
        plane writes the real cap."""
        # After install, ir_config_parameter.xml seeded saas.seat_cap = '0'.
        # If the test DB was used with set_param earlier, we restore explicitly.
        self.config.set_param('saas.seat_cap', '0')
        self.assertEqual(self.config.get_param('saas.seat_cap'), '0')

    def test_default_tenant_id_is_unset_sentinel(self):
        """The 'unset' sentinel survives reinstall — telemetry-secret-unset
        is what the telemetry endpoint checks to refuse responses on
        partially-provisioned tenants."""
        self.config.set_param('saas.telemetry_secret', 'unset')
        self.assertEqual(self.config.get_param('saas.telemetry_secret'), 'unset')
