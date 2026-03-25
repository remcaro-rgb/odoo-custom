from odoo import fields, models


class ClubTournamentMatch(models.Model):
    _name = 'club.tournament.match'
    _description = 'Tournament Match'
    _order = 'id'

    round_id = fields.Many2one(
        'club.tournament.round',
        string='Round',
        required=True,
        ondelete='cascade',
    )
    tournament_id = fields.Many2one(
        related='round_id.tournament_id',
        string='Tournament',
        store=True,
    )
    participant_1_id = fields.Many2one(
        'club.tournament.participant',
        string='Participant 1',
    )
    participant_2_id = fields.Many2one(
        'club.tournament.participant',
        string='Participant 2',
    )
    score_1 = fields.Char(string='Score 1')
    score_2 = fields.Char(string='Score 2')
    winner_id = fields.Many2one(
        'club.tournament.participant',
        string='Winner',
    )
    status = fields.Selection(
        [
            ('scheduled', 'Scheduled'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='scheduled',
        required=True,
    )
    notes = fields.Text(string='Notes')
