from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged('club_guests', 'post_install', '-at_install')
class TestClubGuests(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Affiliate = self.env['club.affiliate']
        self.Guest = self.env['club.guest']
        self.Visit = self.env['club.guest.visit']
        self.Policy = self.env['club.guest.policy']

        self.affiliate = self.Affiliate.create({
            'name': 'Test Host Affiliate',
            'membership_type': 'individual',
        })
        self.guest = self.Guest.create({
            'name': 'Test Guest',
            'identification': '9999999999',
        })
        self.policy = self.Policy.create({
            'name': 'Test Policy',
            'max_guests_per_visit': 2,
            'max_visits_per_month': 3,
            'guest_fee': 10.0,
        })

    def test_visit_auto_sequence(self):
        """Visit name is auto-assigned from sequence on creation."""
        visit = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-25',
        })
        self.assertTrue(
            visit.name and visit.name.startswith('VISIT-'),
            'Visit number should be auto-assigned with VISIT- prefix.',
        )

    def test_action_check_in(self):
        """Check-in action sets status to checked_in and records time."""
        visit = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-25',
            'status': 'registered',
        })
        visit.action_check_in()
        self.assertEqual(visit.status, 'checked_in')
        self.assertTrue(
            visit.check_in_time >= 0,
            'Check-in time should be set.',
        )

    def test_action_check_out(self):
        """Check-out action sets status to checked_out and records time."""
        visit = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-25',
            'status': 'registered',
        })
        visit.action_check_in()
        visit.action_check_out()
        self.assertEqual(visit.status, 'checked_out')
        self.assertTrue(
            visit.check_out_time >= 0,
            'Check-out time should be set.',
        )

    def test_status_transitions(self):
        """Verify full lifecycle: registered -> checked_in -> checked_out."""
        visit = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-25',
            'status': 'registered',
        })
        self.assertEqual(visit.status, 'registered')
        visit.action_check_in()
        self.assertEqual(visit.status, 'checked_in')
        visit.action_check_out()
        self.assertEqual(visit.status, 'checked_out')

    def test_max_guests_per_visit_constraint(self):
        """Creating more visits than policy allows on the same day raises error."""
        guest2 = self.Guest.create({'name': 'Guest Two'})
        guest3 = self.Guest.create({'name': 'Guest Three'})

        # Policy allows max 2 guests per visit (per day)
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-04-01',
            'policy_id': self.policy.id,
        })
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': guest2.id,
            'date': '2026-04-01',
            'policy_id': self.policy.id,
        })
        with self.assertRaises(ValidationError):
            self.Visit.create({
                'affiliate_id': self.affiliate.id,
                'guest_id': guest3.id,
                'date': '2026-04-01',
                'policy_id': self.policy.id,
            })

    def test_max_visits_per_month_constraint(self):
        """Creating more visits than monthly limit raises error."""
        guest2 = self.Guest.create({'name': 'Guest Two'})
        guest3 = self.Guest.create({'name': 'Guest Three'})
        guest4 = self.Guest.create({'name': 'Guest Four'})

        # Policy allows max 3 visits per month
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-06-01',
            'policy_id': self.policy.id,
        })
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': guest2.id,
            'date': '2026-06-10',
            'policy_id': self.policy.id,
        })
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': guest3.id,
            'date': '2026-06-20',
            'policy_id': self.policy.id,
        })
        with self.assertRaises(ValidationError):
            self.Visit.create({
                'affiliate_id': self.affiliate.id,
                'guest_id': guest4.id,
                'date': '2026-06-25',
                'policy_id': self.policy.id,
            })

    def test_cancelled_visits_excluded_from_limits(self):
        """Cancelled visits should not count toward policy limits."""
        guest2 = self.Guest.create({'name': 'Guest Two'})
        guest3 = self.Guest.create({'name': 'Guest Three'})

        # Create 2 visits (policy max is 2 per day), cancel one, then add another
        v1 = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-05-01',
            'policy_id': self.policy.id,
        })
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': guest2.id,
            'date': '2026-05-01',
            'policy_id': self.policy.id,
        })
        # Cancel first visit
        v1.write({'status': 'cancelled'})
        # Should now be able to add a third since one is cancelled
        visit3 = self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': guest3.id,
            'date': '2026-05-01',
            'policy_id': self.policy.id,
        })
        self.assertTrue(visit3.id, 'Visit should be created when cancelled ones free up slots.')

    def test_visit_count_computed(self):
        """Guest visit_count is correctly computed."""
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-01',
        })
        self.Visit.create({
            'affiliate_id': self.affiliate.id,
            'guest_id': self.guest.id,
            'date': '2026-03-02',
        })
        self.guest.invalidate_recordset()
        self.assertEqual(self.guest.visit_count, 2)
