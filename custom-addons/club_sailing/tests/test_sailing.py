from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged('club_sailing', 'post_install', '-at_install')
class TestClubSailing(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Affiliate = self.env['club.affiliate']
        self.Boat = self.env['club.sailing.boat']
        self.Dock = self.env['club.sailing.dock']
        self.Booking = self.env['club.sailing.booking']
        self.Crew = self.env['club.sailing.crew']

        # Create test affiliate
        self.aff1 = self.Affiliate.create({
            'name': 'Sailor One',
            'membership_type': 'individual',
        })
        self.aff2 = self.Affiliate.create({
            'name': 'Sailor Two',
            'membership_type': 'individual',
        })

        # Create test boat
        self.boat = self.Boat.create({
            'name': 'Test Sailboat',
            'boat_type': 'sailboat',
            'capacity': 6,
            'owner_type': 'club',
            'registration_number': 'TST-001',
            'status': 'available',
        })

        # Create test dock
        self.dock = self.Dock.create({
            'name': 'Test Dock',
            'location': 'North area',
            'capacity': 5,
        })

    # ── Boat Double-Booking ──────────────────────────────────

    def test_boat_double_booking_raises(self):
        """Overlapping bookings on same boat and date must raise ValidationError."""
        self.Booking.create({
            'affiliate_id': self.aff1.id,
            'boat_id': self.boat.id,
            'dock_id': self.dock.id,
            'date': '2026-07-01',
            'time_slot': 9.0,
            'duration': 3.0,
            'passenger_count': 4,
            'status': 'booked',
        })
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'affiliate_id': self.aff2.id,
                'boat_id': self.boat.id,
                'dock_id': self.dock.id,
                'date': '2026-07-01',
                'time_slot': 11.0,
                'duration': 2.0,
                'passenger_count': 3,
                'status': 'booked',
            })

    # ── Non-Overlapping Booking Succeeds ─────────────────────

    def test_non_overlapping_booking_same_boat_succeeds(self):
        """Non-overlapping bookings on the same boat should succeed."""
        self.Booking.create({
            'affiliate_id': self.aff1.id,
            'boat_id': self.boat.id,
            'dock_id': self.dock.id,
            'date': '2026-07-01',
            'time_slot': 9.0,
            'duration': 2.0,
            'passenger_count': 4,
            'status': 'booked',
        })
        booking2 = self.Booking.create({
            'affiliate_id': self.aff2.id,
            'boat_id': self.boat.id,
            'dock_id': self.dock.id,
            'date': '2026-07-01',
            'time_slot': 11.0,
            'duration': 2.0,
            'passenger_count': 3,
            'status': 'booked',
        })
        self.assertTrue(
            booking2.id,
            'Non-overlapping booking on same boat should be allowed.'
        )

    # ── Passenger Count Exceeds Capacity ─────────────────────

    def test_passenger_count_exceeds_capacity_raises(self):
        """Passenger count exceeding boat capacity must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'affiliate_id': self.aff1.id,
                'boat_id': self.boat.id,
                'dock_id': self.dock.id,
                'date': '2026-07-02',
                'time_slot': 10.0,
                'duration': 2.0,
                'passenger_count': 10,
                'status': 'booked',
            })

    # ── Duration Exceeds Max ─────────────────────────────────

    def test_duration_exceeds_max_raises(self):
        """Duration exceeding 8 hours must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'affiliate_id': self.aff1.id,
                'boat_id': self.boat.id,
                'dock_id': self.dock.id,
                'date': '2026-07-03',
                'time_slot': 8.0,
                'duration': 9.0,
                'passenger_count': 2,
                'status': 'booked',
            })
