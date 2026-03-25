from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('club_tournaments', 'post_install', '-at_install')
class TestClubTournament(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Tournament = self.env['club.tournament']
        self.Participant = self.env['club.tournament.participant']
        self.Affiliate = self.env['club.affiliate']

        self.affiliate_1 = self.Affiliate.create({
            'name': 'Participant One',
            'membership_type': 'individual',
        })
        self.affiliate_2 = self.Affiliate.create({
            'name': 'Participant Two',
            'membership_type': 'individual',
        })
        self.affiliate_3 = self.Affiliate.create({
            'name': 'Participant Three',
            'membership_type': 'individual',
        })

        self.tournament = self.Tournament.create({
            'title': 'Test Tournament',
            'sport': 'golf',
            'tournament_type': 'single_elimination',
            'start_date': '2026-06-01',
            'end_date': '2026-06-05',
            'max_participants': 2,
        })

    def test_auto_sequence(self):
        """Tournament name is auto-assigned from sequence on creation."""
        self.assertTrue(self.tournament.name)
        self.assertTrue(
            self.tournament.name.startswith('TOURN-'),
            'Tournament name should start with TOURN- prefix.',
        )

    def test_status_draft_to_registration(self):
        """Tournament can transition from draft to registration."""
        self.assertEqual(self.tournament.status, 'draft')
        self.tournament.action_open_registration()
        self.assertEqual(self.tournament.status, 'registration')

    def test_status_registration_to_in_progress(self):
        """Tournament can transition from registration to in_progress."""
        self.tournament.action_open_registration()
        self.tournament.action_start()
        self.assertEqual(self.tournament.status, 'in_progress')

    def test_status_in_progress_to_completed(self):
        """Tournament can transition from in_progress to completed."""
        self.tournament.action_open_registration()
        self.tournament.action_start()
        self.tournament.action_complete()
        self.assertEqual(self.tournament.status, 'completed')

    def test_status_cancel_from_any(self):
        """Tournament can be cancelled from any non-cancelled state."""
        self.tournament.action_cancel()
        self.assertEqual(self.tournament.status, 'cancelled')

    def test_status_invalid_transition_start_from_draft(self):
        """Cannot start a tournament directly from draft."""
        with self.assertRaises(ValidationError):
            self.tournament.action_start()

    def test_status_invalid_transition_complete_from_draft(self):
        """Cannot complete a tournament directly from draft."""
        with self.assertRaises(ValidationError):
            self.tournament.action_complete()

    def test_max_participants_constraint(self):
        """Cannot exceed max_participants on a tournament."""
        self.Participant.create({
            'tournament_id': self.tournament.id,
            'affiliate_id': self.affiliate_1.id,
        })
        self.Participant.create({
            'tournament_id': self.tournament.id,
            'affiliate_id': self.affiliate_2.id,
        })
        with self.assertRaises(ValidationError):
            self.Participant.create({
                'tournament_id': self.tournament.id,
                'affiliate_id': self.affiliate_3.id,
            })

    def test_unique_participant_per_tournament(self):
        """An affiliate cannot participate twice in the same tournament."""
        self.Participant.create({
            'tournament_id': self.tournament.id,
            'affiliate_id': self.affiliate_1.id,
        })
        with self.assertRaises(Exception):
            self.Participant.create({
                'tournament_id': self.tournament.id,
                'affiliate_id': self.affiliate_1.id,
            })

    def test_participant_count_computed(self):
        """participant_count reflects the number of participants."""
        self.assertEqual(self.tournament.participant_count, 0)
        self.Participant.create({
            'tournament_id': self.tournament.id,
            'affiliate_id': self.affiliate_1.id,
        })
        self.tournament.invalidate_recordset()
        self.assertEqual(self.tournament.participant_count, 1)
        self.Participant.create({
            'tournament_id': self.tournament.id,
            'affiliate_id': self.affiliate_2.id,
        })
        self.tournament.invalidate_recordset()
        self.assertEqual(self.tournament.participant_count, 2)
