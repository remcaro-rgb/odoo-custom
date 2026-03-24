from odoo import api, fields, models, _


class ClubTennisRanking(models.Model):
    _name = 'club.tennis.ranking'
    _description = 'Tennis Ranking'
    _order = 'category, rank, points desc'

    affiliate_id = fields.Many2one(
        'club.affiliate', required=True, string='Affiliate',
        ondelete='cascade',
    )
    category = fields.Selection(
        [
            ('men', 'Men'),
            ('women', 'Women'),
            ('junior', 'Junior'),
            ('senior', 'Senior'),
            ('mixed', 'Mixed'),
        ],
        string='Category',
        required=True,
    )
    points = fields.Integer(string='Points', default=0)
    rank = fields.Integer(string='Rank', default=0)
    matches_played = fields.Integer(string='Matches Played', default=0)
    matches_won = fields.Integer(string='Matches Won', default=0)

    _sql_constraints = [
        (
            'affiliate_category_uniq',
            'unique(affiliate_id, category)',
            'An affiliate can only have one ranking per category.',
        ),
    ]

    @api.model
    def recompute_ranks(self, category):
        """Recompute rank for all records in the given category,
        sorted by points descending."""
        self.env.flush_all()
        self.env.invalidate_all()
        rankings = self.search(
            [('category', '=', category)],
            order='points desc, id asc',
        )
        for position, ranking in enumerate(rankings, start=1):
            ranking.with_context(recomputing_rank=True).write({'rank': position})
