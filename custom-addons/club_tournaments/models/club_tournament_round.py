from odoo import fields, models


class ClubTournamentRound(models.Model):
    _name = 'club.tournament.round'
    _description = 'Tournament Round'
    _order = 'round_number, id'

    tournament_id = fields.Many2one(
        'club.tournament',
        string='Tournament',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(
        string='Round Name',
        required=True,
        help='e.g. Round 1, Quarterfinals, Semifinals, Final',
    )
    round_number = fields.Integer(string='Round Number', default=1)
    date = fields.Date(string='Date')
    match_ids = fields.One2many(
        'club.tournament.match',
        'round_id',
        string='Matches',
    )
