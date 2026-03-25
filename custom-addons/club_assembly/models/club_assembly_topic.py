from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubAssemblyTopic(models.Model):
    _name = 'club.assembly.topic'
    _description = 'Assembly Topic'
    _order = 'sequence, id'

    assembly_id = fields.Many2one(
        'club.assembly',
        string='Assembly',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    name = fields.Char(
        string='Topic',
        required=True,
    )
    description = fields.Html(
        string='Description',
    )
    topic_type = fields.Selection(
        [
            ('informative', 'Informative'),
            ('discussion', 'Discussion'),
            ('voting', 'Voting'),
        ],
        string='Type',
        default='informative',
    )
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_discussion', 'In Discussion'),
            ('voting_open', 'Voting Open'),
            ('voting_closed', 'Voting Closed'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('tabled', 'Tabled'),
        ],
        string='Status',
        default='pending',
    )
    vote_ids = fields.One2many(
        'club.assembly.vote',
        'topic_id',
        string='Votes',
    )
    votes_for = fields.Integer(
        string='Votes For',
        compute='_compute_vote_counts',
        store=True,
    )
    votes_against = fields.Integer(
        string='Votes Against',
        compute='_compute_vote_counts',
        store=True,
    )
    votes_abstain = fields.Integer(
        string='Votes Abstain',
        compute='_compute_vote_counts',
        store=True,
    )
    vote_result = fields.Char(
        string='Vote Result',
        compute='_compute_vote_counts',
        store=True,
    )
    resolution = fields.Html(
        string='Resolution',
    )
    notes = fields.Text(
        string='Notes',
    )

    # ---- Computed fields ----------------------------------------------------

    @api.depends('vote_ids', 'vote_ids.vote', 'status')
    def _compute_vote_counts(self):
        for rec in self:
            votes = rec.vote_ids
            rec.votes_for = len(votes.filtered(lambda v: v.vote == 'for'))
            rec.votes_against = len(
                votes.filtered(lambda v: v.vote == 'against')
            )
            rec.votes_abstain = len(
                votes.filtered(lambda v: v.vote == 'abstain')
            )
            if rec.status in ('approved', 'rejected', 'voting_closed'):
                f, a, ab = rec.votes_for, rec.votes_against, rec.votes_abstain
                if rec.status == 'approved' or (
                    rec.status == 'voting_closed' and f > a
                ):
                    rec.vote_result = _(
                        'Aprobado (%s-%s-%s)', f, a, ab
                    )
                elif rec.status == 'rejected' or (
                    rec.status == 'voting_closed' and a >= f
                ):
                    rec.vote_result = _(
                        'Rechazado (%s-%s-%s)', f, a, ab
                    )
                else:
                    rec.vote_result = _('Pendiente')
            else:
                rec.vote_result = _('Pendiente')

    # ---- Workflow actions ---------------------------------------------------

    def action_open_discussion(self):
        for rec in self:
            if rec.status != 'pending':
                raise UserError(
                    _('Only pending topics can be opened for discussion.')
                )
            rec.status = 'in_discussion'

    def action_open_voting(self):
        for rec in self:
            if rec.status != 'in_discussion':
                raise UserError(
                    _('Only topics in discussion can be opened for voting.')
                )
            rec.status = 'voting_open'

    def action_close_voting(self):
        for rec in self:
            if rec.status != 'voting_open':
                raise UserError(
                    _('Only topics with open voting can be closed.')
                )
            if rec.votes_for > rec.votes_against:
                rec.status = 'approved'
            else:
                rec.status = 'rejected'

    def action_table(self):
        for rec in self:
            rec.status = 'tabled'
