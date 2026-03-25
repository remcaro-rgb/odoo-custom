from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubTournamentParticipant(models.Model):
    _name = 'club.tournament.participant'
    _description = 'Tournament Participant'
    _order = 'seed, id'
    _rec_name = 'affiliate_id'

    tournament_id = fields.Many2one(
        'club.tournament',
        string='Tournament',
        required=True,
        ondelete='cascade',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        required=True,
    )
    registration_date = fields.Date(
        string='Registration Date',
        default=fields.Date.context_today,
    )
    seed = fields.Integer(string='Seed', default=0)
    status = fields.Selection(
        [
            ('registered', 'Registered'),
            ('active', 'Active'),
            ('eliminated', 'Eliminated'),
            ('winner', 'Winner'),
            ('withdrawn', 'Withdrawn'),
        ],
        string='Status',
        default='registered',
        required=True,
    )
    final_position = fields.Integer(string='Final Position')
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'unique_participant_per_tournament',
            'unique(tournament_id, affiliate_id)',
            'An affiliate can only participate once per tournament.',
        ),
    ]

    @api.constrains('tournament_id')
    def _check_max_participants(self):
        for participant in self:
            tournament = participant.tournament_id
            if (
                tournament.max_participants > 0
                and tournament.participant_count > tournament.max_participants
            ):
                raise ValidationError(
                    _(
                        'Tournament "%(tournament)s" has reached the maximum '
                        'number of participants (%(max)s).',
                        tournament=tournament.title,
                        max=tournament.max_participants,
                    )
                )
