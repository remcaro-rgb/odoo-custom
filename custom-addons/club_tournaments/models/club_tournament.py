from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubTournament(models.Model):
    _name = 'club.tournament'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Club Tournament'
    _order = 'start_date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: _('New'),
    )
    title = fields.Char(
        string='Tournament Name',
        required=True,
        tracking=True,
    )
    sport = fields.Selection(
        [
            ('golf', 'Golf'),
            ('tennis', 'Tennis'),
            ('equestrian', 'Equestrian'),
            ('sailing', 'Sailing'),
            ('swimming', 'Swimming'),
            ('other', 'Other'),
        ],
        string='Sport',
        required=True,
        tracking=True,
    )
    tournament_type = fields.Selection(
        [
            ('single_elimination', 'Single Elimination'),
            ('double_elimination', 'Double Elimination'),
            ('round_robin', 'Round Robin'),
            ('league', 'League'),
        ],
        string='Tournament Type',
        required=True,
        tracking=True,
    )
    description = fields.Html(string='Description')
    start_date = fields.Date(
        string='Start Date',
        required=True,
        tracking=True,
    )
    end_date = fields.Date(
        string='End Date',
        required=True,
        tracking=True,
    )
    max_participants = fields.Integer(
        string='Max Participants',
        default=0,
        help='Maximum number of participants. 0 means unlimited.',
    )
    entry_fee = fields.Float(string='Entry Fee')
    prize_description = fields.Text(string='Prize Description')
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('registration', 'Registration'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    organizer_id = fields.Many2one(
        'res.users',
        string='Organizer',
        default=lambda self: self.env.user,
        tracking=True,
    )
    participant_ids = fields.One2many(
        'club.tournament.participant',
        'tournament_id',
        string='Participants',
    )
    round_ids = fields.One2many(
        'club.tournament.round',
        'tournament_id',
        string='Rounds',
    )
    participant_count = fields.Integer(
        string='Participant Count',
        compute='_compute_participant_count',
        store=True,
    )

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for tournament in self:
            tournament.participant_count = len(tournament.participant_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.tournament'
                ) or _('New')
        return super().create(vals_list)

    def action_open_registration(self):
        for rec in self:
            if rec.status != 'draft':
                raise ValidationError(
                    _('Only draft tournaments can be opened for registration.')
                )
            rec.status = 'registration'

    def action_start(self):
        for rec in self:
            if rec.status != 'registration':
                raise ValidationError(
                    _('Only tournaments in registration can be started.')
                )
            rec.status = 'in_progress'

    def action_complete(self):
        for rec in self:
            if rec.status != 'in_progress':
                raise ValidationError(
                    _('Only in-progress tournaments can be completed.')
                )
            rec.status = 'completed'

    def action_cancel(self):
        for rec in self:
            if rec.status == 'cancelled':
                raise ValidationError(
                    _('This tournament is already cancelled.')
                )
            rec.status = 'cancelled'
