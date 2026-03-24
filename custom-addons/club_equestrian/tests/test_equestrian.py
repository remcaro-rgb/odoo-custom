from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged('club_equestrian', 'post_install', '-at_install')
class TestClubEquestrian(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Horse = self.env['club.horse']
        self.Stall = self.env['club.stall']
        self.Arena = self.env['club.arena']
        self.Booking = self.env['club.equestrian.booking']

        # Create a test affiliate (active member)
        product = self.env['product.product'].create({
            'name': 'Test Plan Product',
            'type': 'service',
        })
        plan = self.env['club.membership.plan'].create({
            'name': 'Test Plan',
            'fee': 100.0,
            'billing_period': 'annual',
            'product_id': product.id,
        })
        self.affiliate = self.env['club.affiliate'].create({
            'name': 'Test Owner',
            'membership_type': 'individual',
        })
        self.env['club.membership'].create({
            'affiliate_id': self.affiliate.id,
            'plan_id': plan.id,
            'start_date': '2026-01-01',
            'status': 'active',
        })
        self.affiliate.invalidate_recordset()

        # A second affiliate for constraint testing
        self.affiliate_other = self.env['club.affiliate'].create({
            'name': 'Other Owner',
            'membership_type': 'individual',
        })
        self.env['club.membership'].create({
            'affiliate_id': self.affiliate_other.id,
            'plan_id': plan.id,
            'start_date': '2026-01-01',
            'status': 'active',
        })
        self.affiliate_other.invalidate_recordset()

        # Create a test arena
        self.arena = self.Arena.create({
            'name': 'Test Arena',
            'arena_type': 'multipurpose',
            'capacity': 4,
        })

    # ── Horse registration number ─────────────────────────────────

    def test_horse_registration_number_auto(self):
        """Horse gets an auto-generated registration number on create."""
        horse = self.Horse.create({
            'name': 'Test Horse',
            'owner_id': self.affiliate.id,
        })
        self.assertTrue(
            horse.registration_number,
            'Registration number should be auto-assigned.',
        )
        self.assertTrue(
            horse.registration_number.startswith('EQ'),
            'Registration number should start with EQ prefix.',
        )

    def test_horse_registration_number_unique(self):
        """Each horse gets a unique registration number."""
        h1 = self.Horse.create({
            'name': 'Horse A',
            'owner_id': self.affiliate.id,
        })
        h2 = self.Horse.create({
            'name': 'Horse B',
            'owner_id': self.affiliate.id,
        })
        self.assertNotEqual(
            h1.registration_number,
            h2.registration_number,
            'Two horses must have different registration numbers.',
        )

    # ── Stall computed fields ─────────────────────────────────────

    def test_stall_horse_id_computed(self):
        """Stall.horse_id is computed from the horse assigned to it."""
        stall = self.Stall.create({'name': 'S-1'})
        horse = self.Horse.create({
            'name': 'Stall Horse',
            'owner_id': self.affiliate.id,
            'stall_id': stall.id,
        })
        stall.invalidate_recordset()
        self.assertEqual(
            stall.horse_id.id,
            horse.id,
            'Stall horse_id should reflect the horse assigned to it.',
        )

    def test_stall_status_vacant(self):
        """Stall with no horse and not under maintenance is vacant."""
        stall = self.Stall.create({'name': 'S-Empty'})
        self.assertEqual(stall.status, 'vacant')

    def test_stall_status_occupied(self):
        """Stall with a horse assigned is occupied."""
        stall = self.Stall.create({'name': 'S-Occ'})
        self.Horse.create({
            'name': 'Occ Horse',
            'owner_id': self.affiliate.id,
            'stall_id': stall.id,
        })
        stall.invalidate_recordset()
        self.assertEqual(stall.status, 'occupied')

    def test_stall_status_maintenance(self):
        """Stall under maintenance shows maintenance status."""
        stall = self.Stall.create({
            'name': 'S-Maint',
            'under_maintenance': True,
        })
        self.assertEqual(stall.status, 'maintenance')

    def test_stall_status_maintenance_overrides_occupied(self):
        """Maintenance flag overrides occupied status."""
        stall = self.Stall.create({
            'name': 'S-Override',
            'under_maintenance': True,
        })
        self.Horse.create({
            'name': 'Override Horse',
            'owner_id': self.affiliate.id,
            'stall_id': stall.id,
        })
        stall.invalidate_recordset()
        self.assertEqual(
            stall.status,
            'maintenance',
            'Maintenance should override occupied status.',
        )

    # ── Booking constraints ───────────────────────────────────────

    def test_booking_max_duration(self):
        """Booking duration cannot exceed 2 hours."""
        horse = self.Horse.create({
            'name': 'Duration Horse',
            'owner_id': self.affiliate.id,
        })
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'arena_id': self.arena.id,
                'affiliate_id': self.affiliate.id,
                'horse_id': horse.id,
                'date': '2026-06-01',
                'time_slot': 10.0,
                'duration': 3.0,
                'status': 'booked',
            })

    def test_booking_horse_owner_mismatch(self):
        """Horse owner must match the booking affiliate."""
        horse = self.Horse.create({
            'name': 'Owned Horse',
            'owner_id': self.affiliate.id,
        })
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'arena_id': self.arena.id,
                'affiliate_id': self.affiliate_other.id,
                'horse_id': horse.id,
                'date': '2026-06-01',
                'time_slot': 10.0,
                'duration': 1.0,
                'status': 'booked',
            })

    def test_booking_overlap_detection(self):
        """Overlapping bookings on the same arena and date are rejected."""
        horse1 = self.Horse.create({
            'name': 'Overlap Horse 1',
            'owner_id': self.affiliate.id,
        })
        horse2 = self.Horse.create({
            'name': 'Overlap Horse 2',
            'owner_id': self.affiliate_other.id,
        })
        # First booking: 10:00 - 11:00
        self.Booking.create({
            'arena_id': self.arena.id,
            'affiliate_id': self.affiliate.id,
            'horse_id': horse1.id,
            'date': '2026-07-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        # Overlapping booking: 10:30 - 11:30
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'arena_id': self.arena.id,
                'affiliate_id': self.affiliate_other.id,
                'horse_id': horse2.id,
                'date': '2026-07-01',
                'time_slot': 10.5,
                'duration': 1.0,
                'status': 'booked',
            })

    def test_booking_no_overlap_adjacent(self):
        """Adjacent bookings (no overlap) are allowed."""
        horse1 = self.Horse.create({
            'name': 'Adjacent Horse 1',
            'owner_id': self.affiliate.id,
        })
        horse2 = self.Horse.create({
            'name': 'Adjacent Horse 2',
            'owner_id': self.affiliate_other.id,
        })
        # First booking: 10:00 - 11:00
        self.Booking.create({
            'arena_id': self.arena.id,
            'affiliate_id': self.affiliate.id,
            'horse_id': horse1.id,
            'date': '2026-08-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        # Adjacent booking: 11:00 - 12:00 — should succeed
        booking2 = self.Booking.create({
            'arena_id': self.arena.id,
            'affiliate_id': self.affiliate_other.id,
            'horse_id': horse2.id,
            'date': '2026-08-01',
            'time_slot': 11.0,
            'duration': 1.0,
            'status': 'booked',
        })
        self.assertTrue(booking2.id, 'Adjacent booking should be created.')
