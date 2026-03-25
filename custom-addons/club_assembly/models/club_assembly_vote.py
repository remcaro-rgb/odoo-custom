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
        help='The assembly member whose vote this represents.',
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
    is_proxy_vote = fields.Boolean(
        string='Proxy Vote',
        default=False,
        help='This vote was cast by a proxy holder on behalf of the member.',
    )
    proxy_voter_id = fields.Many2one(
        'club.affiliate',
        string='Voted By (Proxy)',
        help='The affiliate who physically cast this vote under power of attorney.',
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

    @api.constrains('is_proxy_vote', 'proxy_voter_id', 'affiliate_id')
    def _check_proxy_authorization(self):
        """If this is a proxy vote, verify the proxy_voter_id holds a valid
        power of attorney (Poder) for the affiliate in this assembly."""
        for rec in self:
            if not rec.is_proxy_vote:
                continue
            if not rec.proxy_voter_id:
                raise ValidationError(
                    _('Proxy votes must specify who cast the vote '
                      '(Voted By proxy field).')
                )
            assembly = rec.topic_id.assembly_id
            # Check that the affiliate's attendance record has status='proxy'
            # and proxy_holder_id matches the proxy_voter_id
            attendance = self.env['club.assembly.attendance'].search([
                ('assembly_id', '=', assembly.id),
                ('affiliate_id', '=', rec.affiliate_id.id),
                ('status', '=', 'proxy'),
                ('proxy_holder_id', '=', rec.proxy_voter_id.id),
            ], limit=1)
            if not attendance:
                raise ValidationError(
                    _(
                        '"%(proxy)s" does not have a valid authorization '
                        '(Poder) to vote on behalf of "%(member)s" in this '
                        'assembly. Please register the proxy in the '
                        'attendance tab first.',
                        proxy=rec.proxy_voter_id.display_name,
                        member=rec.affiliate_id.display_name,
                    )
                )
