from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError


@tagged('club_golf', 'post_install', '-at_install')
class TestClubGolf(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Affiliate = self.env['club.affiliate']
        self.Course = self.env['club.golf.course']
        self.TeeTime = self.env['club.golf.tee.time']
        self.Caddie = self.env['club.golf.caddie']
        self.Cart = self.env['club.golf.cart']
        self.Bag = self.env['club.golf.bag']
        self.Scorecard = self.env['club.golf.scorecard']
        self.ScorecardLine = self.env['club.golf.scorecard.line']
        self.Handicap = self.env['club.golf.handicap']

        # Create a test course
        self.course = self.Course.create({
            'name': 'Test Course',
            'holes': 18,
            'par': 72,
            'slope_rating': 130.0,
            'course_rating': 72.5,
        })

        # Create test affiliates
        self.aff1 = self.Affiliate.create({
            'name': 'Player One',
            'membership_type': 'individual',
        })
        self.aff2 = self.Affiliate.create({
            'name': 'Player Two',
            'membership_type': 'individual',
        })
        self.aff3 = self.Affiliate.create({
            'name': 'Player Three',
            'membership_type': 'individual',
        })
        self.aff4 = self.Affiliate.create({
            'name': 'Player Four',
            'membership_type': 'individual',
        })
        self.aff5 = self.Affiliate.create({
            'name': 'Player Five',
            'membership_type': 'individual',
        })

        # Create test caddie
        self.caddie = self.Caddie.create({
            'partner_id': self.env['res.partner'].create({
                'name': 'Test Caddie'
            }).id,
            'employee_number': 'TC-001',
        })

        # Create test cart
        self.cart = self.Cart.create({
            'name': 'T-01',
            'cart_type': 'rental',
            'status': 'available',
        })

    # ── Tee Time Conflict ──────────────────────────────────────

    def test_tee_time_conflict_same_course_date_time(self):
        """Two tee times on the same course, date and time_slot must raise."""
        self.TeeTime.create({
            'date': '2026-06-01',
            'time_slot': 7.0,
            'course_id': self.course.id,
            'status': 'booked',
        })
        with self.assertRaises(ValidationError):
            self.TeeTime.create({
                'date': '2026-06-01',
                'time_slot': 7.0,
                'course_id': self.course.id,
                'status': 'booked',
            })

    def test_tee_time_different_time_slot_ok(self):
        """Different time_slot on same course and date is allowed."""
        self.TeeTime.create({
            'date': '2026-06-01',
            'time_slot': 7.0,
            'course_id': self.course.id,
            'status': 'booked',
        })
        tt2 = self.TeeTime.create({
            'date': '2026-06-01',
            'time_slot': 7.5,
            'course_id': self.course.id,
            'status': 'booked',
        })
        self.assertTrue(tt2.id, 'Different time slot should be allowed.')

    # ── Caddie Double-Booking ──────────────────────────────────

    def test_caddie_double_booking(self):
        """Same caddie at same date+time must raise ValidationError."""
        self.TeeTime.create({
            'date': '2026-06-01',
            'time_slot': 7.0,
            'course_id': self.course.id,
            'caddie_id': self.caddie.id,
            'status': 'booked',
        })
        course2 = self.Course.create({
            'name': 'Other Course',
            'holes': 9,
            'par': 36,
            'slope_rating': 120.0,
            'course_rating': 35.5,
        })
        with self.assertRaises(ValidationError):
            self.TeeTime.create({
                'date': '2026-06-01',
                'time_slot': 7.0,
                'course_id': course2.id,
                'caddie_id': self.caddie.id,
                'status': 'booked',
            })

    # ── Max 4 Affiliates ───────────────────────────────────────

    def test_max_four_affiliates(self):
        """More than 4 affiliates on a tee time must raise."""
        with self.assertRaises(ValidationError):
            self.TeeTime.create({
                'date': '2026-06-02',
                'time_slot': 8.0,
                'course_id': self.course.id,
                'affiliate_ids': [(6, 0, [
                    self.aff1.id, self.aff2.id, self.aff3.id,
                    self.aff4.id, self.aff5.id,
                ])],
                'status': 'booked',
            })

    def test_four_affiliates_allowed(self):
        """Exactly 4 affiliates should be allowed."""
        tt = self.TeeTime.create({
            'date': '2026-06-02',
            'time_slot': 8.0,
            'course_id': self.course.id,
            'affiliate_ids': [(6, 0, [
                self.aff1.id, self.aff2.id, self.aff3.id, self.aff4.id,
            ])],
            'status': 'booked',
        })
        self.assertEqual(len(tt.affiliate_ids), 4)

    # ── Scorecard Computed Fields ──────────────────────────────

    def _create_scorecard_with_lines(self, affiliate, date, scores):
        """Helper: create a scorecard with given per-hole scores."""
        pars = [4, 4, 3, 5, 4, 4, 3, 5, 4, 4, 4, 3, 5, 4, 4, 3, 5, 4]
        sc = self.Scorecard.create({
            'affiliate_id': affiliate.id,
            'course_id': self.course.id,
            'date': date,
            'line_ids': [(0, 0, {
                'hole_number': i + 1,
                'par': pars[i],
                'score': score,
            }) for i, score in enumerate(scores)],
        })
        return sc

    def test_gross_score_computed(self):
        """Gross score should be the sum of all hole scores."""
        scores = [5, 4, 4, 6, 5, 4, 4, 6, 5, 5, 4, 3, 5, 5, 4, 4, 6, 5]
        sc = self._create_scorecard_with_lines(self.aff1, '2026-06-01', scores)
        self.assertEqual(sc.gross_score, sum(scores))

    def test_score_differential_computation(self):
        """Score differential = (113 / slope) * (gross - course_rating)."""
        scores = [5, 4, 4, 6, 5, 4, 4, 6, 5, 5, 4, 3, 5, 5, 4, 4, 6, 5]
        sc = self._create_scorecard_with_lines(self.aff2, '2026-06-01', scores)
        gross = sum(scores)
        expected = round((113.0 / 130.0) * (gross - 72.5), 1)
        self.assertAlmostEqual(sc.score_differential, expected, places=1)

    # ── Handicap Index Calculation ─────────────────────────────

    def test_handicap_index_with_three_scorecards(self):
        """With exactly 3 scorecards the lowest 1 differential is used."""
        # Round 1: gross 84
        scores1 = [5, 4, 4, 6, 5, 4, 4, 6, 5, 5, 4, 3, 5, 5, 4, 4, 6, 5]
        sc1 = self._create_scorecard_with_lines(self.aff3, '2026-06-01', scores1)

        # Round 2: gross 80
        scores2 = [4, 4, 3, 5, 4, 5, 3, 5, 4, 4, 5, 4, 5, 4, 4, 3, 5, 5]
        sc2 = self._create_scorecard_with_lines(self.aff3, '2026-06-08', scores2)

        # Round 3: gross 78
        scores3 = [4, 4, 3, 5, 4, 4, 3, 5, 4, 4, 4, 3, 5, 4, 4, 3, 5, 4]
        sc3 = self._create_scorecard_with_lines(self.aff3, '2026-06-15', scores3)

        # With 3 rounds, use lowest 1 differential
        differentials = sorted([
            sc1.score_differential,
            sc2.score_differential,
            sc3.score_differential,
        ])
        expected_index = round(differentials[0] * 0.96, 1)

        handicap = self.env['club.golf.handicap'].search(
            [('affiliate_id', '=', self.aff3.id)], limit=1
        )
        self.assertTrue(handicap, 'Handicap record should be auto-created.')
        self.assertAlmostEqual(
            handicap.handicap_index, expected_index, places=1,
            msg='Handicap index should use lowest 1 of 3 differentials * 0.96.'
        )

    def test_handicap_index_fewer_than_three_is_zero(self):
        """With fewer than 3 scorecards the handicap index stays 0.0."""
        scores1 = [5, 4, 4, 6, 5, 4, 4, 6, 5, 5, 4, 3, 5, 5, 4, 4, 6, 5]
        self._create_scorecard_with_lines(self.aff4, '2026-06-01', scores1)

        scores2 = [4, 4, 3, 5, 4, 5, 3, 5, 4, 4, 5, 4, 5, 4, 4, 3, 5, 5]
        self._create_scorecard_with_lines(self.aff4, '2026-06-08', scores2)

        handicap = self.env['club.golf.handicap'].search(
            [('affiliate_id', '=', self.aff4.id)], limit=1
        )
        self.assertTrue(handicap, 'Handicap record should exist.')
        self.assertEqual(
            handicap.handicap_index, 0.0,
            'Handicap index should be 0.0 with fewer than 3 scorecards.'
        )

    # ── Bag Tag Uniqueness ─────────────────────────────────────

    def test_bag_tag_number_unique(self):
        """Duplicate bag tag numbers must raise an integrity error."""
        self.Bag.create({
            'tag_number': 'UNIQ-001',
            'owner_id': self.aff1.id,
        })
        with self.assertRaises(Exception):
            self.Bag.create({
                'tag_number': 'UNIQ-001',
                'owner_id': self.aff2.id,
            })

    # ── Cart Double-Assignment ─────────────────────────────────

    def test_rental_cart_double_assignment(self):
        """Rental cart at same date+time must raise."""
        self.TeeTime.create({
            'date': '2026-06-03',
            'time_slot': 9.0,
            'course_id': self.course.id,
            'cart_id': self.cart.id,
            'status': 'booked',
        })
        course2 = self.Course.create({
            'name': 'Other Course 2',
            'holes': 18,
            'par': 72,
            'slope_rating': 125.0,
            'course_rating': 71.0,
        })
        with self.assertRaises(ValidationError):
            self.TeeTime.create({
                'date': '2026-06-03',
                'time_slot': 9.0,
                'course_id': course2.id,
                'cart_id': self.cart.id,
                'status': 'booked',
            })
