from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo import fields


@tagged('club_access_control', 'post_install', '-at_install')
class TestAccessControl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Partner / Affiliate with active membership ──────────────
        cls.partner_active = cls.env['res.partner'].create({
            'name': 'Test Active Affiliate',
            'vat': '9999000001',
        })
        cls.affiliate_active = cls.env['club.affiliate'].create({
            'partner_id': cls.partner_active.id,
            'membership_type': 'individual',
        })
        cls.plan = cls.env['club.membership.plan'].search([], limit=1)
        if not cls.plan:
            product = cls.env['product.product'].create({
                'name': 'Test Membership Product',
                'type': 'service',
                'list_price': 100.0,
            })
            cls.plan = cls.env['club.membership.plan'].create({
                'name': 'Test Plan',
                'fee': 100.0,
                'billing_period': 'annual',
                'grace_period_days': 15,
                'product_id': product.id,
            })
        cls.membership_active = cls.env['club.membership'].create({
            'affiliate_id': cls.affiliate_active.id,
            'plan_id': cls.plan.id,
            'start_date': fields.Date.today(),
            'status': 'active',
        })

        # ── Partner / Affiliate with inactive (expired) membership ──
        cls.partner_inactive = cls.env['res.partner'].create({
            'name': 'Test Inactive Affiliate',
            'vat': '9999000002',
        })
        cls.affiliate_inactive = cls.env['club.affiliate'].create({
            'partner_id': cls.partner_inactive.id,
            'membership_type': 'individual',
        })
        cls.membership_expired = cls.env['club.membership'].create({
            'affiliate_id': cls.affiliate_inactive.id,
            'plan_id': cls.plan.id,
            'start_date': fields.Date.today(),
            'status': 'expired',
        })

        # ── Family dependent affiliate ──────────────────────────────
        cls.partner_dependent = cls.env['res.partner'].create({
            'name': 'Test Family Dependent',
            'vat': '9999000003',
        })
        cls.affiliate_dependent = cls.env['club.affiliate'].create({
            'partner_id': cls.partner_dependent.id,
            'membership_type': 'family_dependent',
        })
        cls.membership_dependent = cls.env['club.membership'].create({
            'affiliate_id': cls.affiliate_dependent.id,
            'plan_id': cls.plan.id,
            'start_date': fields.Date.today(),
            'status': 'active',
        })

        # ── Employee type ───────────────────────────────────────────
        cls.employee_type = cls.env['club.employee.type'].search([], limit=1)
        if not cls.employee_type:
            cls.employee_type = cls.env['club.employee.type'].create({
                'name': 'Test Type',
            })

        # ── Employee with active employer ───────────────────────────
        cls.employee_active = cls.env['club.affiliate.employee'].create({
            'name': 'Test Active Employee',
            'affiliate_id': cls.affiliate_active.id,
            'employee_type_id': cls.employee_type.id,
            'identification_number': 'EMP-ID-001',
            'access_card_number': 'CARD-001',
            'status': 'active',
        })

        # ── Employee suspended ──────────────────────────────────────
        cls.employee_suspended = cls.env['club.affiliate.employee'].create({
            'name': 'Test Suspended Employee',
            'affiliate_id': cls.affiliate_active.id,
            'employee_type_id': cls.employee_type.id,
            'identification_number': 'EMP-ID-002',
            'access_card_number': 'CARD-002',
            'status': 'suspended',
        })

        # ── Vehicle ─────────────────────────────────────────────────
        cls.vehicle = cls.env['club.access.vehicle'].create({
            'affiliate_id': cls.affiliate_active.id,
            'plate_number': 'TEST-999',
            'vehicle_type': 'car',
            'brand': 'Toyota',
        })

        # ── Checkpoint ──────────────────────────────────────────────
        cls.checkpoint = cls.env['club.access.checkpoint'].create({
            'name': 'Test Gate',
            'checkpoint_type': 'main_gate',
        })

        # ── Guest with today visit ──────────────────────────────────
        cls.guest = cls.env['club.guest'].create({
            'name': 'Test Guest',
            'identification': '8888000001',
        })
        cls.guest_visit = cls.env['club.guest.visit'].search([
            ('guest_id', '=', cls.guest.id),
        ], limit=1)
        if not cls.guest_visit:
            cls.guest_visit = cls.env['club.guest.visit'].create({
                'affiliate_id': cls.affiliate_active.id,
                'guest_id': cls.guest.id,
                'date': fields.Date.today(),
                'status': 'registered',
            })

        # ── Supplier + staff ────────────────────────────────────────
        cls.supplier_partner = cls.env['res.partner'].create({
            'name': 'Test Supplier Co.',
            'is_company': True,
        })
        cls.supplier = cls.env['club.access.supplier'].create({
            'partner_id': cls.supplier_partner.id,
        })
        cls.supplier_staff = cls.env['club.access.supplier.staff'].create({
            'supplier_id': cls.supplier.id,
            'name': 'Test Staff Member',
            'identification_number': 'SUP-ID-001',
            'status': 'active',
        })

    # ── Helper ──────────────────────────────────────────────────────

    def _create_entry(self, method='membership_card', value=''):
        return self.env['club.access.entry'].create({
            'checkpoint_id': self.checkpoint.id,
            'identification_method': method,
            'identification_value': value,
        })

    # ── Tests ───────────────────────────────────────────────────────

    def test_lookup_membership_card(self):
        """Affiliate number lookup finds affiliate with active membership."""
        entry = self._create_entry('membership_card', self.affiliate_active.affiliate_number)
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'affiliate')
        self.assertEqual(entry.affiliate_id, self.affiliate_active)

    def test_lookup_membership_card_inactive(self):
        """Inactive membership results in denied access."""
        entry = self._create_entry('membership_card', self.affiliate_inactive.affiliate_number)
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'denied')
        self.assertTrue(entry.denial_reason)

    def test_lookup_membership_card_family_dependent(self):
        """Family dependent is identified correctly."""
        entry = self._create_entry('membership_card', self.affiliate_dependent.affiliate_number)
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'family_member')

    def test_lookup_access_card(self):
        """Employee access card lookup with active employer membership."""
        entry = self._create_entry('access_card', 'CARD-001')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'affiliate_employee')
        self.assertEqual(entry.employee_id, self.employee_active)

    def test_lookup_access_card_suspended_employee(self):
        """Suspended employee is denied even if employer is active."""
        entry = self._create_entry('access_card', 'CARD-002')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'denied')
        self.assertTrue(entry.denial_reason, 'Denial reason should be set for suspended employee.')

    def test_lookup_vehicle_plate(self):
        """Vehicle plate lookup finds vehicle and maps to affiliate."""
        entry = self._create_entry('vehicle_plate', 'TEST-999')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'affiliate')
        self.assertEqual(entry.affiliate_id, self.affiliate_active)
        self.assertEqual(entry.vehicle_id, self.vehicle)

    def test_lookup_vehicle_plate_case_insensitive(self):
        """Vehicle plate lookup is case-insensitive."""
        entry = self._create_entry('vehicle_plate', 'test-999')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.vehicle_id, self.vehicle)

    def test_lookup_gov_id_affiliate(self):
        """VAT lookup finds affiliate."""
        entry = self._create_entry('gov_id', '9999000001')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'affiliate')
        self.assertEqual(entry.affiliate_id, self.affiliate_active)

    def test_lookup_gov_id_employee(self):
        """Identification number finds employee."""
        entry = self._create_entry('gov_id', 'EMP-ID-001')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'affiliate_employee')
        self.assertEqual(entry.employee_id, self.employee_active)

    def test_lookup_gov_id_supplier(self):
        """Identification number finds supplier staff."""
        entry = self._create_entry('gov_id', 'SUP-ID-001')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'supplier_staff')
        self.assertEqual(entry.supplier_staff_id, self.supplier_staff)

    def test_lookup_gov_id_guest(self):
        """Guest identification finds guest with today's visit."""
        entry = self._create_entry('gov_id', '8888000001')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        self.assertEqual(entry.person_type, 'guest')
        self.assertEqual(entry.guest_id, self.guest)

    def test_lookup_no_match(self):
        """No match results in denied access."""
        entry = self._create_entry('membership_card', 'NONEXISTENT')
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'denied')
        self.assertTrue(entry.denial_reason, 'Denial reason should be set for no match.')

    def test_lookup_empty_value(self):
        """Empty identifier raises UserError."""
        entry = self._create_entry('membership_card', '')
        with self.assertRaises(UserError):
            entry.action_lookup()

    def test_exit_action(self):
        """Exit sets exit_datetime and status to exited."""
        entry = self._create_entry('membership_card', self.affiliate_active.affiliate_number)
        entry.action_lookup()
        self.assertEqual(entry.access_status, 'granted')
        entry.action_exit()
        self.assertEqual(entry.access_status, 'exited')
        self.assertTrue(entry.exit_datetime)
        self.assertFalse(entry.is_active_entry)

    def test_exit_non_granted_raises(self):
        """Exiting a non-granted entry raises UserError."""
        entry = self._create_entry('membership_card', '')
        with self.assertRaises(UserError):
            entry.action_exit()

    def test_vehicle_plate_unique(self):
        """SQL constraint prevents duplicate plate numbers."""
        with self.assertRaises(Exception):
            self.env['club.access.vehicle'].create({
                'affiliate_id': self.affiliate_active.id,
                'plate_number': 'TEST-999',
                'vehicle_type': 'car',
            })

    def test_entry_auto_sequence(self):
        """Entry name is auto-generated with ACC- prefix."""
        entry = self._create_entry('membership_card', 'X')
        self.assertTrue(entry.name.startswith('ACC-'))

    def test_manual_grant(self):
        """Manually granting a pending entry works."""
        entry = self._create_entry('membership_card', '')
        entry.action_grant()
        self.assertEqual(entry.access_status, 'granted')

    def test_manual_deny(self):
        """Manually denying a pending entry with reason."""
        entry = self._create_entry('membership_card', '')
        entry.action_deny('Test denial reason')
        self.assertEqual(entry.access_status, 'denied')
        self.assertEqual(entry.denial_reason, 'Test denial reason')

    def test_duration_computed(self):
        """Duration is computed after exit."""
        entry = self._create_entry('membership_card', self.affiliate_active.affiliate_number)
        entry.action_lookup()
        # Set entry_datetime to 1 hour ago to ensure measurable duration
        from datetime import timedelta
        entry.entry_datetime = fields.Datetime.now() - timedelta(hours=1)
        entry.action_exit()
        self.assertGreater(entry.duration_minutes, 0.0)
