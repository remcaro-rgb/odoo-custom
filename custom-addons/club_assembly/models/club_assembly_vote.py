from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ClubAssemblyVote(models.Model):
    _name = 'club.assembly.vote'
    _description = 'Assembly Vote'
    _order = 'voted_at desc'

    topic_id = fields.Many2one(
        'club.assembly.topic',
        string='Topic',
        required=True,
        ondelete='cascade',
    )
    assembly_id = fields.Many2one(
        related='topic_id.assembly_id',
        string='Assembly',
        store=True,
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Voter',
        required=True,
    )
    vote = fields.Selection(
        [
            ('for', 'For'),
            ('against', 'Against'),
            ('abstain', 'Abstain'),
        ],
        string='Vote',
        required=True,
    )
    voted_at = fields.Datetime(
        string='Voted At',
        default=fields.Datetime.now,
    )
    notes = fields.Char(
        string='Notes',
    )

    _sql_constraints = [
        (
            'unique_topic_affiliate',
            'UNIQUE(topic_id, affiliate_id)',
            'Each affiliate can only vote once per topic.',
        ),
    ]

    @api.constrains('affiliate_id', 'topic_id')
    def _check_voter_is_member(self):
        for rec in self:
            assembly = rec.topic_id.assembly_id
            if rec.affiliate_id not in assembly.member_ids:
                raise ValidationError(
                    _(
                        'Voter "%(voter)s" is not a member of assembly '
                        '"%(assembly)s".',
                        voter=rec.affiliate_id.display_name,
                        assembly=assembly.display_name,
                    )
                )
