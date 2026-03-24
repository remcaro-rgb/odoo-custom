from odoo import api, fields, models, _


class ClubGolfScorecard(models.Model):
    _name = 'club.golf.scorecard'
    _description = 'Golf Scorecard'
    _order = 'date desc'

    tee_time_id = fields.Many2one(
        'club.golf.tee.time', string='Tee Time',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
    )
    course_id = fields.Many2one(
        'club.golf.course', required=True, string='Course',
    )
    date = fields.Date(string='Date', required=True)
    line_ids = fields.One2many(
        'club.golf.scorecard.line', 'scorecard_id',
        string='Hole Scores',
    )
    gross_score = fields.Integer(
        string='Gross Score',
        compute='_compute_scores',
        store=True,
    )
    course_handicap = fields.Integer(
        string='Course Handicap',
        compute='_compute_scores',
        store=True,
    )
    net_score = fields.Integer(
        string='Net Score',
        compute='_compute_scores',
        store=True,
    )
    score_differential = fields.Float(
        string='Score Differential',
        compute='_compute_scores',
        store=True,
        digits=(6, 1),
    )

    @api.depends('line_ids.score', 'affiliate_id', 'course_id',
                 'course_id.slope_rating', 'course_id.course_rating')
    def _compute_scores(self):
        for sc in self:
            gross = sum(sc.line_ids.mapped('score'))
            sc.gross_score = gross

            # Course handicap from affiliate's handicap index + course data
            handicap_rec = self.env['club.golf.handicap'].search(
                [('affiliate_id', '=', sc.affiliate_id.id)], limit=1
            )
            handicap_index = handicap_rec.handicap_index if handicap_rec else 0.0
            slope = sc.course_id.slope_rating or 113.0
            course_rating = sc.course_id.course_rating or 0.0
            sc.course_handicap = round(handicap_index * (slope / 113.0))
            sc.net_score = gross - sc.course_handicap

            # Score differential: WHS formula
            if slope and gross:
                sc.score_differential = round(
                    (113.0 / slope) * (gross - course_rating), 1
                )
            else:
                sc.score_differential = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._update_handicaps()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._update_handicaps()
        return res

    def _update_handicaps(self):
        """Recalculate handicap index for each affected affiliate."""
        self.env.flush_all()
        Handicap = self.env['club.golf.handicap']
        for sc in self:
            if not sc.affiliate_id:
                continue
            handicap = Handicap.search(
                [('affiliate_id', '=', sc.affiliate_id.id)], limit=1
            )
            if not handicap:
                handicap = Handicap.create({
                    'affiliate_id': sc.affiliate_id.id,
                    'handicap_index': 0.0,
                    'revision_date': fields.Date.today(),
                })
            handicap._recompute_handicap_index()


class ClubGolfScorecardLine(models.Model):
    _name = 'club.golf.scorecard.line'
    _description = 'Golf Scorecard Line'
    _order = 'hole_number'

    scorecard_id = fields.Many2one(
        'club.golf.scorecard', required=True, ondelete='cascade',
        string='Scorecard',
    )
    hole_number = fields.Integer(string='Hole', required=True)
    par = fields.Integer(string='Par', required=True)
    score = fields.Integer(string='Score', required=True)
