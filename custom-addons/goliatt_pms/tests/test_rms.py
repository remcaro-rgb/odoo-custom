from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('goliatt_pms', 'post_install', '-at_install')
class TestRmsAndKiosk(TransactionCase):
    """Tests for the RMS engine and Kiosk check-in features."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.property = cls.env['pms.property'].create({
            'name': 'RMS Test Hotel',
            'code': 'RMS01',
            'property_type': 'hotel',
            'star_rating': '4',
            'check_in_time': 15.0,
            'check_out_time': 11.0,
        })
        cls.room_type = cls.env['pms.room.type'].create({
            'name': 'RMS Standard',
            'code': 'RMSTD',
            'property_id': cls.property.id,
            'max_adults': 2,
            'max_children': 1,
            'bed_type': 'queen',
            'base_rate': 200000,
        })
        cls.room_1 = cls.env['pms.room'].create({
            'name': 'R101',
            'room_type_id': cls.room_type.id,
            'floor': '1',
            'status': 'available',
            'housekeeping_status': 'clean',
        })
        cls.room_2 = cls.env['pms.room'].create({
            'name': 'R102',
            'room_type_id': cls.room_type.id,
            'floor': '1',
            'status': 'available',
            'housekeeping_status': 'inspected',
        })
        cls.guest = cls.env['res.partner'].create({
            'name': 'RMS Test Guest',
            'email': 'rmstest@example.com',
            'is_hotel_guest': True,
            'guest_id_type': 'passport',
            'guest_id_number': 'PP-TEST-001',
        })
        cls.today = date.today()

    def _create_reservation(self, **kwargs):
        vals = {
            'property_id': self.property.id,
            'guest_id': self.guest.id,
            'checkin_date': self.today,
            'checkout_date': self.today + timedelta(days=3),
            'room_type_id': self.room_type.id,
            'adults': 1,
            'daily_rate': 200000,
        }
        vals.update(kwargs)
        return self.env['pms.reservation'].create(vals)

    # ------------------------------------------------------------------
    # 1. RMS engine generates recommendations
    # ------------------------------------------------------------------
    def test_01_rms_generates_recommendations(self):
        """Running the RMS engine creates recommendation records."""
        self.property.action_run_rms()
        recs = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
        ])
        # Should generate 90 days worth for the one room type
        self.assertEqual(len(recs), 90)

    # ------------------------------------------------------------------
    # 2. Occupancy-based rule fires correctly
    # ------------------------------------------------------------------
    def test_02_occupancy_rule_fires(self):
        """Occupancy-based rule increases rate when occupancy is high."""
        # Create enough reservations to push occupancy above threshold
        # We have 2 rooms. 1 reservation = 50% occupancy.
        self._create_reservation(
            room_id=self.room_1.id,
            checkin_date=self.today,
            checkout_date=self.today + timedelta(days=1),
        )
        self._create_reservation(
            room_id=self.room_2.id,
            checkin_date=self.today,
            checkout_date=self.today + timedelta(days=1),
            guest_id=self.env['res.partner'].create({
                'name': 'Guest 2',
                'is_hotel_guest': True,
            }).id,
        )
        # 2/2 rooms = 100% occupancy
        rule = self.env['pms.revenue.rule'].create({
            'name': 'Test Occupancy Rule',
            'property_id': self.property.id,
            'rule_type': 'occupancy_based',
            'occupancy_min': 90,
            'occupancy_max': 100,
            'action_type': 'multiplier',
            'multiplier': 1.50,
            'priority': 1,
        })
        self.property.action_run_rms()
        rec = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
            ('date', '=', self.today),
        ], limit=1)
        # Rate should be adjusted upwards
        self.assertGreater(rec.recommended_rate, rec.current_rate)
        self.assertIn(rule.name, rec.rules_applied)

    # ------------------------------------------------------------------
    # 3. Lead-time rule fires correctly
    # ------------------------------------------------------------------
    def test_03_lead_time_rule_fires(self):
        """Lead-time rule applies to dates far in advance."""
        rule = self.env['pms.revenue.rule'].create({
            'name': 'Test Early Bird',
            'property_id': self.property.id,
            'rule_type': 'lead_time',
            'lead_time_min': 30,
            'lead_time_max': 365,
            'action_type': 'multiplier',
            'multiplier': 0.85,
            'priority': 1,
        })
        self.property.action_run_rms()
        # Check a date 60 days from now (lead_time=60, within 30-365)
        target = self.today + timedelta(days=60)
        rec = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
            ('date', '=', target),
        ], limit=1)
        self.assertTrue(rec)
        self.assertIn(rule.name, rec.rules_applied)
        # Rate should be discounted
        self.assertLess(rec.recommended_rate, rec.current_rate)

    # ------------------------------------------------------------------
    # 4. Accept recommendation updates availability
    # ------------------------------------------------------------------
    def test_04_accept_updates_availability(self):
        """Accepting a recommendation creates/updates pms.availability."""
        self.property.action_run_rms()
        rec = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
            ('status', '=', 'pending'),
        ], limit=1)
        self.assertTrue(rec)
        rec.action_accept()
        self.assertEqual(rec.status, 'accepted')
        avail = self.env['pms.availability'].search([
            ('property_id', '=', self.property.id),
            ('room_type_id', '=', rec.room_type_id.id),
            ('date', '=', rec.date),
        ], limit=1)
        self.assertTrue(avail)
        self.assertEqual(avail.rate, rec.recommended_rate)

    # ------------------------------------------------------------------
    # 5. Reject recommendation
    # ------------------------------------------------------------------
    def test_05_reject_recommendation(self):
        """Rejecting a recommendation sets status to rejected."""
        self.property.action_run_rms()
        rec = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
            ('status', '=', 'pending'),
        ], limit=1)
        rec.action_reject()
        self.assertEqual(rec.status, 'rejected')
        # Rejecting again should raise
        with self.assertRaises(UserError):
            rec.action_reject()

    # ------------------------------------------------------------------
    # 6. Multiplier calculation correct
    # ------------------------------------------------------------------
    def test_06_multiplier_calculation(self):
        """A multiplier rule correctly adjusts the rate."""
        # Create a competitor rule (always fires) with 1.10 multiplier
        self.env['pms.revenue.rule'].create({
            'name': 'Test 10% Increase',
            'property_id': self.property.id,
            'rule_type': 'competitor',
            'action_type': 'multiplier',
            'multiplier': 1.10,
            'priority': 1,
        })
        self.property.action_run_rms()
        rec = self.env['pms.revenue.recommendation'].search([
            ('property_id', '=', self.property.id),
            ('date', '=', self.today),
        ], limit=1)
        # Base rate 200000 * 1.10 = 220000, rounded to nearest 1000
        self.assertEqual(rec.recommended_rate, 220000)

    # ------------------------------------------------------------------
    # 7. Kiosk session lifecycle
    # ------------------------------------------------------------------
    def test_07_kiosk_session_lifecycle(self):
        """Kiosk session goes through scan -> confirm -> complete."""
        reservation = self._create_reservation(room_id=self.room_1.id)
        session = self.env['pms.kiosk.session'].create({
            'property_id': self.property.id,
            'reservation_id': reservation.id,
            'guest_id': self.guest.id,
            'session_type': 'checkin',
            'status': 'started',
        })
        self.assertTrue(session.name.startswith('KIOSK-'))
        self.assertEqual(session.status, 'started')

        # Scan ID
        session.action_scan_id()
        self.assertEqual(session.status, 'id_scanned')
        self.assertEqual(session.id_document_number, 'PP-TEST-001')

        # Confirm
        session.action_confirm_checkin()
        self.assertEqual(session.status, 'confirmed')

        # Complete
        session.action_complete_checkin()
        self.assertEqual(session.status, 'completed')
        self.assertEqual(reservation.state, 'checked_in')
        self.assertTrue(session.key_issued)
        self.assertEqual(session.room_assigned, self.room_1.name)

    # ------------------------------------------------------------------
    # 8. Kiosk auto-assigns room on checkin
    # ------------------------------------------------------------------
    def test_08_kiosk_auto_assigns_room(self):
        """Kiosk auto-assigns an available clean room when none is set."""
        reservation = self._create_reservation()
        # No room_id set
        self.assertFalse(reservation.room_id)

        session = self.env['pms.kiosk.session'].create({
            'property_id': self.property.id,
            'reservation_id': reservation.id,
            'guest_id': self.guest.id,
            'session_type': 'checkin',
            'status': 'confirmed',
        })
        session.action_complete_checkin()
        self.assertEqual(session.status, 'completed')
        self.assertTrue(reservation.room_id)
        self.assertEqual(reservation.state, 'checked_in')
        self.assertTrue(session.room_assigned)
