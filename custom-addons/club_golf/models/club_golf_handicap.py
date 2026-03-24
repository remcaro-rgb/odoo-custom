from odoo import api, fields, models, _


class ClubGolfHandicap(models.Model):
    _name = 'club.golf.handicap'
    _description = 'Golf Handicap'
    _rec_name = 'affiliate_id'

    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
    )
    handicap_index = fields.Float(
        string='Handicap Index', digits=(5, 1), default=0.0,
    )
    revision_date = fields.Date(string='Revision Date')
    history_ids = fields.One2many(
        'club.golf.handicap.history', 'handicap_id',
        string='History',
    )

    _sql_constraints = [
        ('affiliate_uniq', 'unique(affiliate_id)',
         'Each affiliate can have only one handicap record.'),
    ]

    def _recompute_handicap_index(self):
        """Recalculate handicap index based on WHS rules."""
        for handicap in self:
            scorecards = self.env['club.golf.scorecard'].search(
                [('affiliate_id', '=', handicap.affiliate_id.id)],
                order='date desc',
                limit=20,
            )
            count = len(scorecards)
            if count < 3:
                handicap.handicap_index = 0.0
                handicap.revision_date = fields.Date.today()
                continue

            differentials = sorted(scorecards.mapped('score_differential'))

            # Determine how many lowest differentials to use
            if count <= 6:
                n = 1
            elif count <= 8:
                n = 2
            elif count <= 11:
                n = 3
            elif count <= 14:
                n = 4
            elif count <= 16:
                n = 5
            elif count <= 18:
                n = 6
            elif count == 19:
                n = 7
            else:
                n = 8

            lowest = differentials[:n]
            avg = sum(lowest) / len(lowest) if lowest else 0.0
            new_index = round(avg * 0.96, 1)

            handicap.handicap_index = new_index
            handicap.revision_date = fields.Date.today()

            # Create history entry
            self.env['club.golf.handicap.history'].create({
                'handicap_id': handicap.id,
                'date': fields.Date.today(),
                'handicap_index': new_index,
                'scorecard_ids': [(6, 0, scorecards.ids)],
            })


class ClubGolfHandicapHistory(models.Model):
    _name = 'club.golf.handicap.history'
    _description = 'Golf Handicap History'
    _order = 'date desc'

    handicap_id = fields.Many2one(
        'club.golf.handicap', required=True, ondelete='cascade',
        string='Handicap',
    )
    date = fields.Date(string='Date', required=True)
    handicap_index = fields.Float(
        string='Handicap Index', digits=(5, 1),
    )
    scorecard_ids = fields.Many2many(
        'club.golf.scorecard',
        'club_golf_handicap_history_scorecard_rel',
        'history_id', 'scorecard_id',
        string='Scorecards Used',
    )
