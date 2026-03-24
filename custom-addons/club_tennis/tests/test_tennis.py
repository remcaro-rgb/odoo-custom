from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged('club_tennis', 'post_install', '-at_install')
class TestTennisBooking(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Court = self.env['club.tennis.court']
        self.Booking = self.env['club.tennis.booking']
        self.Caddie = self.env['club.tennis.caddie']
        self.Match = self.env['club.tennis.match']
        self.Ranking = self.env['club.tennis.ranking']
        self.Affiliate = self.env['club.affiliate']

        # Courts
        self.court_1 = self.Court.create({
            'name': 'Test Court 1',
            'surface': 'clay',
        })
        self.court_2 = self.Court.create({
            'name': 'Test Court 2',
            'surface': 'hard',
        })

        # Affiliates
        self.aff_1 = self.Affiliate.create({
            'name': 'Player One',
            'membership_type': 'individual',
        })
        self.aff_2 = self.Affiliate.create({
            'name': 'Player Two',
            'membership_type': 'individual',
        })
        self.aff_3 = self.Affiliate.create({
            'name': 'Player Three',
            'membership_type': 'individual',
        })
        self.aff_4 = self.Affiliate.create({
            'name': 'Player Four',
            'membership_type': 'individual',
        })
        self.aff_5 = self.Affiliate.create({
            'name': 'Player Five',
            'membership_type': 'individual',
        })

        # Caddies
        partner_caddie = self.env['res.partner'].create({
            'name': 'Test Caddie',
        })
        self.caddie = self.Caddie.create({
            'partner_id': partner_caddie.id,
            'employee_number': 'TC-TEST-01',
        })

    # ── Court Overlap Tests ──────────────────────────────────────

    def test_court_booking_overlap_raises(self):
        """Overlapping bookings on the same court should raise ValidationError."""
        self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-01',
            'time_slot': 10.0,
            'duration': 2.0,
            'status': 'booked',
        })
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'court_id': self.court_1.id,
                'date': '2026-05-01',
                'time_slot': 11.0,
                'duration': 1.0,
                'status': 'booked',
            })

    def test_court_booking_no_overlap_different_court(self):
        """Same time on different courts should be allowed."""
        self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        booking_2 = self.Booking.create({
            'court_id': self.court_2.id,
            'date': '2026-05-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        self.assertTrue(booking_2.id, 'Booking on a different court should succeed.')

    def test_court_booking_cancelled_not_blocking(self):
        """A cancelled booking should not block new bookings."""
        self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-01',
            'time_slot': 10.0,
            'duration': 2.0,
            'status': 'cancelled',
        })
        booking_2 = self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        self.assertTrue(booking_2.id, 'Cancelled booking should not block.')

    # ── Caddie Double-Booking Tests ──────────────────────────────

    def test_caddie_double_booking_raises(self):
        """Same caddie at overlapping times should raise ValidationError."""
        self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-02',
            'time_slot': 9.0,
            'duration': 2.0,
            'caddie_id': self.caddie.id,
            'status': 'booked',
        })
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'court_id': self.court_2.id,
                'date': '2026-05-02',
                'time_slot': 10.0,
                'duration': 1.0,
                'caddie_id': self.caddie.id,
                'status': 'booked',
            })

    # ── Max 4 Affiliates Tests ───────────────────────────────────

    def test_max_4_affiliates(self):
        """More than 4 affiliates per booking should raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'court_id': self.court_1.id,
                'date': '2026-05-03',
                'time_slot': 8.0,
                'duration': 1.0,
                'affiliate_ids': [(6, 0, [
                    self.aff_1.id, self.aff_2.id, self.aff_3.id,
                    self.aff_4.id, self.aff_5.id,
                ])],
                'status': 'booked',
            })

    def test_4_affiliates_allowed(self):
        """Exactly 4 affiliates should be allowed."""
        booking = self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-03',
            'time_slot': 8.0,
            'duration': 1.0,
            'affiliate_ids': [(6, 0, [
                self.aff_1.id, self.aff_2.id, self.aff_3.id, self.aff_4.id,
            ])],
            'status': 'booked',
        })
        self.assertEqual(len(booking.affiliate_ids), 4)

    # ── Duration Constraint Tests ────────────────────────────────

    def test_duration_must_be_1_or_2(self):
        """Duration of 1.5 hours should raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.Booking.create({
                'court_id': self.court_1.id,
                'date': '2026-05-04',
                'time_slot': 10.0,
                'duration': 1.5,
                'status': 'booked',
            })

    def test_duration_1_hour_allowed(self):
        """Duration of 1 hour should be allowed."""
        booking = self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-04',
            'time_slot': 10.0,
            'duration': 1.0,
            'status': 'booked',
        })
        self.assertEqual(booking.duration, 1.0)

    def test_duration_2_hours_allowed(self):
        """Duration of 2 hours should be allowed."""
        booking = self.Booking.create({
            'court_id': self.court_1.id,
            'date': '2026-05-04',
            'time_slot': 14.0,
            'duration': 2.0,
            'status': 'booked',
        })
        self.assertEqual(booking.duration, 2.0)


@tagged('club_tennis', 'post_install', '-at_install')
class TestTennisMatchRanking(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Court = self.env['club.tennis.court']
        self.Booking = self.env['club.tennis.booking']
        self.Match = self.env['club.tennis.match']
        self.Ranking = self.env['club.tennis.ranking']
        self.Affiliate = self.env['club.affiliate']

        self.court = self.Court.create({
            'name': 'Ranking Court',
            'surface': 'hard',
        })

        self.player_a = self.Affiliate.create({
            'name': 'Rank Player A',
            'membership_type': 'individual',
        })
        self.player_b = self.Affiliate.create({
            'name': 'Rank Player B',
            'membership_type': 'individual',
        })
        self.player_c = self.Affiliate.create({
            'name': 'Rank Player C',
            'membership_type': 'individual',
        })

        # Initial rankings in 'senior' category (avoids demo data conflicts)
        self.rank_a = self.Ranking.create({
            'affiliate_id': self.player_a.id,
            'category': 'senior',
            'points': 100,
            'rank': 1,
            'matches_played': 5,
            'matches_won': 4,
        })
        self.rank_b = self.Ranking.create({
            'affiliate_id': self.player_b.id,
            'category': 'senior',
            'points': 80,
            'rank': 2,
            'matches_played': 5,
            'matches_won': 3,
        })
        self.rank_c = self.Ranking.create({
            'affiliate_id': self.player_c.id,
            'category': 'senior',
            'points': 60,
            'rank': 3,
            'matches_played': 4,
            'matches_won': 2,
        })

        self.booking = self.Booking.create({
            'court_id': self.court.id,
            'date': '2026-06-01',
            'time_slot': 10.0,
            'duration': 1.0,
            'affiliate_ids': [(6, 0, [self.player_a.id, self.player_b.id])],
            'status': 'completed',
        })

    # ── Match Ranking Update Tests ────────────────────────────────

    def test_match_updates_winner_ranking(self):
        """Creating a match with a winner should update winner's points,
        matches_played, and matches_won."""
        self.Match.create({
            'booking_id': self.booking.id,
            'player_ids': [(6, 0, [self.player_a.id, self.player_b.id])],
            'set_1_score': '6-3',
            'set_2_score': '6-4',
            'winner_id': self.player_b.id,
            'ranking_points_awarded': 20,
        })
        self.rank_b.invalidate_recordset()
        self.assertEqual(self.rank_b.points, 100,
                         'Winner points should increase by 20 (80+20=100).')
        self.assertEqual(self.rank_b.matches_played, 6,
                         'Winner matches_played should increment by 1.')
        self.assertEqual(self.rank_b.matches_won, 4,
                         'Winner matches_won should increment by 1.')

    def test_match_updates_loser_ranking(self):
        """Creating a match should update loser's matches_played only."""
        self.Match.create({
            'booking_id': self.booking.id,
            'player_ids': [(6, 0, [self.player_a.id, self.player_b.id])],
            'set_1_score': '6-3',
            'set_2_score': '6-4',
            'winner_id': self.player_b.id,
            'ranking_points_awarded': 20,
        })
        self.rank_a.invalidate_recordset()
        self.assertEqual(self.rank_a.points, 100,
                         'Loser points should remain unchanged.')
        self.assertEqual(self.rank_a.matches_played, 6,
                         'Loser matches_played should increment by 1.')
        self.assertEqual(self.rank_a.matches_won, 4,
                         'Loser matches_won should remain unchanged.')

    def test_rank_recomputation_after_match(self):
        """After a match that changes the points, ranks should be recomputed."""
        # Player B (80pts) wins 25 points -> becomes 105, overtaking Player A (100)
        self.Match.create({
            'booking_id': self.booking.id,
            'player_ids': [(6, 0, [self.player_a.id, self.player_b.id])],
            'set_1_score': '7-5',
            'set_2_score': '6-2',
            'winner_id': self.player_b.id,
            'ranking_points_awarded': 25,
        })
        # Explicitly flush, invalidate, and recompute
        self.env.flush_all()
        self.env.invalidate_all()
        # Verify points updated
        rank_b = self.Ranking.browse(self.rank_b.id)
        self.assertEqual(rank_b.points, 105,
                         'Player B points should be 105 (80+25).')
        # Explicitly recompute ranks
        self.Ranking.recompute_ranks('senior')
        self.env.flush_all()
        self.env.invalidate_all()
        rank_b = self.Ranking.browse(self.rank_b.id)
        rank_a = self.Ranking.browse(self.rank_a.id)
        rank_c = self.Ranking.browse(self.rank_c.id)
        # B: 105, A: 100, C: 60
        self.assertEqual(rank_b.rank, 1,
                         'Player B should now be rank 1 with 105 points.')
        self.assertEqual(rank_a.rank, 2,
                         'Player A should now be rank 2 with 100 points.')
        self.assertEqual(rank_c.rank, 3,
                         'Player C should remain rank 3.')

    # ── Ranking Unique Constraint Test ────────────────────────────

    def test_ranking_unique_affiliate_category(self):
        """Duplicate affiliate+category in ranking should raise IntegrityError."""
        from psycopg2 import IntegrityError
        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.Ranking.create({
                    'affiliate_id': self.player_a.id,
                    'category': 'senior',
                    'points': 50,
                })
