from odoo.exceptions import ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('club_swimming', 'post_install', '-at_install')
class TestSwimmingBooking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Swimmer',
            'email': 'swimmer@test.com',
        })
        cls.affiliate = cls.env['club.affiliate'].create({
            'partner_id': cls.partner.id,
            'membership_type': 'individual',
        })
        cls.pool = cls.env['club.swimming.pool'].create({
            'name': 'Test Pool',
            'pool_type': 'olympic',
            'lane_count': 4,
            'max_capacity': 20,
            'under_maintenance': False,
        })
        cls.lane = cls.env['club.swimming.lane'].create({
            'pool_id': cls.pool.id,
            'name': 'Lane 1',
            'lane_type': 'lap',
            'status': 'available',
        })

    def test_lane_double_booking_raises(self):
        """Lane double-booking on overlapping time raises ValidationError."""
        self.env['club.swimming.booking'].create({
            'affiliate_id': self.affiliate.id,
            'pool_id': self.pool.id,
            'lane_id': self.lane.id,
            'date': '2026-04-01',
            'time_slot': 8.0,
            'duration': 2.0,
            'status': 'booked',
        })
        with self.assertRaises(ValidationError):
            self.env['club.swimming.booking'].create({
                'affiliate_id': self.affiliate.id,
                'pool_id': self.pool.id,
                'lane_id': self.lane.id,
                'date': '2026-04-01',
                'time_slot': 9.0,
                'duration': 1.5,
                'status': 'booked',
            })

    def test_duration_max_3_raises(self):
        """Duration exceeding 3 hours raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['club.swimming.booking'].create({
                'affiliate_id': self.affiliate.id,
                'pool_id': self.pool.id,
                'date': '2026-04-02',
                'time_slot': 8.0,
                'duration': 4.0,
                'status': 'booked',
            })

    def test_maintenance_pool_raises(self):
        """Booking a pool under maintenance raises ValidationError."""
        self.pool.write({'under_maintenance': True})
        with self.assertRaises(ValidationError):
            self.env['club.swimming.booking'].create({
                'affiliate_id': self.affiliate.id,
                'pool_id': self.pool.id,
                'date': '2026-04-03',
                'time_slot': 8.0,
                'duration': 1.0,
                'status': 'booked',
            })

    def test_valid_booking_succeeds(self):
        """A valid booking is created without errors."""
        booking = self.env['club.swimming.booking'].create({
            'affiliate_id': self.affiliate.id,
            'pool_id': self.pool.id,
            'lane_id': self.lane.id,
            'date': '2026-04-04',
            'time_slot': 10.0,
            'duration': 1.5,
            'status': 'booked',
        })
        self.assertEqual(booking.status, 'booked')
        self.assertEqual(booking.duration, 1.5)
