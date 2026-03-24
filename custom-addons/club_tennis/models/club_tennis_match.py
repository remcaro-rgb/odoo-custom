from odoo import api, fields, models, _


class ClubTennisMatch(models.Model):
    _name = 'club.tennis.match'
    _description = 'Tennis Match'

    booking_id = fields.Many2one(
        'club.tennis.booking', string='Booking',
        ondelete='set null',
    )
    player_ids = fields.Many2many(
        'club.affiliate', string='Players',
    )
    set_1_score = fields.Char(string='Set 1 Score')
    set_2_score = fields.Char(string='Set 2 Score')
    set_3_score = fields.Char(string='Set 3 Score')
    winner_id = fields.Many2one(
        'club.affiliate', string='Winner',
    )
    ranking_points_awarded = fields.Integer(
        string='Ranking Points Awarded', default=0,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for match in records:
            if match.winner_id and match.ranking_points_awarded:
                match._update_rankings()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'winner_id' in vals or 'ranking_points_awarded' in vals:
            for match in self:
                if match.winner_id and match.ranking_points_awarded:
                    match._update_rankings()
        return res

    def _update_rankings(self):
        """Update ranking records for winner and losers after a match result.

        Winner: points += ranking_points_awarded, matches_played += 1,
                 matches_won += 1.
        Losers (other players): matches_played += 1.
        After update, recompute rank for all affected categories.
        """
        self.ensure_one()
        Ranking = self.env['club.tennis.ranking']
        affected_categories = set()

        # --- Winner ---
        winner_rankings = Ranking.search([
            ('affiliate_id', '=', self.winner_id.id),
        ])
        if winner_rankings:
            for wr in winner_rankings:
                wr.write({
                    'points': wr.points + self.ranking_points_awarded,
                    'matches_played': wr.matches_played + 1,
                    'matches_won': wr.matches_won + 1,
                })
                affected_categories.add(wr.category)

        # --- Losers ---
        losers = self.player_ids - self.winner_id
        for loser in losers:
            loser_rankings = Ranking.search([
                ('affiliate_id', '=', loser.id),
            ])
            for lr in loser_rankings:
                lr.write({
                    'matches_played': lr.matches_played + 1,
                })
                affected_categories.add(lr.category)

        # --- Recompute ranks ---
        self.env.flush_all()
        for category in affected_categories:
            Ranking.recompute_ranks(category)
