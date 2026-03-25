from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubAssembly(models.Model):
    _name = 'club.assembly'
    _description = 'Club Assembly'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Number',
        readonly=True,
        copy=False,
        default='/',
    )
    title = fields.Char(
        string='Title',
        required=True,
    )
    assembly_type = fields.Selection(
        [
            ('ordinary', 'Ordinaria'),
            ('extraordinary', 'Extraordinaria'),
        ],
        string='Type',
        default='ordinary',
    )
    description = fields.Html(
        string='Description',
    )
    date = fields.Datetime(
        string='Date',
        required=True,
    )
    location = fields.Char(
        string='Location',
    )
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('scheduled', 'Scheduled'),
            ('in_session', 'In Session'),
            ('voting', 'Voting'),
            ('closed', 'Closed'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        tracking=True,
        string='Status',
    )
    president_id = fields.Many2one(
        'club.affiliate',
        string='President',
    )
    secretary_id = fields.Many2one(
        'club.affiliate',
        string='Secretary',
    )
    member_ids = fields.Many2many(
        'club.affiliate',
        'club_assembly_member_rel',
        'assembly_id',
        'affiliate_id',
        string='Assembly Members',
    )
    topic_ids = fields.One2many(
        'club.assembly.topic',
        'assembly_id',
        string='Topics',
    )
    attendance_ids = fields.One2many(
        'club.assembly.attendance',
        'assembly_id',
        string='Attendance',
    )
    member_count = fields.Integer(
        string='Member Count',
        compute='_compute_member_count',
        store=True,
    )
    quorum_required = fields.Integer(
        string='Quorum Required',
        default=0,
        help='Minimum attendees for a valid session. 0 means no quorum check.',
    )
    quorum_met = fields.Boolean(
        string='Quorum Met',
        compute='_compute_quorum_met',
        store=True,
    )
    transcript = fields.Html(
        string='Transcript',
    )
    summary = fields.Html(
        string='Summary',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'club_assembly_attachment_rel',
        'assembly_id',
        'attachment_id',
        string='Attachments',
    )

    # ---- Computed fields ----------------------------------------------------

    @api.depends('member_ids')
    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.member_ids)

    @api.depends(
        'attendance_ids',
        'attendance_ids.status',
        'quorum_required',
    )
    def _compute_quorum_met(self):
        for rec in self:
            if rec.quorum_required == 0:
                rec.quorum_met = True
            else:
                present_count = len(
                    rec.attendance_ids.filtered(
                        lambda a: a.status == 'present'
                    )
                )
                rec.quorum_met = present_count >= rec.quorum_required

    # ---- CRUD overrides -----------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.assembly'
                ) or '/'
        return super().create(vals_list)

    # ---- Workflow actions ---------------------------------------------------

    def action_schedule(self):
        for rec in self:
            if rec.status != 'draft':
                raise UserError(
                    _('Only draft assemblies can be scheduled.')
                )
            rec.status = 'scheduled'

    def action_send_invitations(self):
        template = self.env.ref(
            'club_assembly.mail_template_assembly_invitation'
        )
        for rec in self:
            if rec.status != 'scheduled':
                raise UserError(
                    _('Invitations can only be sent for scheduled assemblies.')
                )
            count = 0
            for member in rec.member_ids:
                partner = member.partner_id
                if partner.email:
                    template.send_mail(
                        rec.id,
                        force_send=False,
                        email_values={
                            'email_to': partner.email,
                        },
                    )
                    count += 1
            rec.message_post(
                body=_('%d invitation(s) queued for sending.', count),
            )

    def action_open_session(self):
        for rec in self:
            if rec.status != 'scheduled':
                raise UserError(
                    _('Only scheduled assemblies can be opened.')
                )
            if rec.quorum_required and not rec.quorum_met:
                raise UserError(
                    _(
                        'Quorum not met. Required: %(required)s, '
                        'Present: %(present)s.',
                        required=rec.quorum_required,
                        present=len(
                            rec.attendance_ids.filtered(
                                lambda a: a.status == 'present'
                            )
                        ),
                    )
                )
            rec.status = 'in_session'

    def action_start_voting(self):
        for rec in self:
            if rec.status != 'in_session':
                raise UserError(
                    _('Only in-session assemblies can start voting.')
                )
            rec.status = 'voting'

    def action_close(self):
        for rec in self:
            if rec.status not in ('in_session', 'voting'):
                raise UserError(
                    _(
                        'Only in-session or voting assemblies can be closed.'
                    )
                )
            rec.status = 'closed'

    def action_cancel(self):
        for rec in self:
            if rec.status == 'closed':
                raise UserError(
                    _('Closed assemblies cannot be cancelled.')
                )
            rec.status = 'cancelled'

    def action_add_all_active_affiliates(self):
        active_affiliates = self.env['club.affiliate'].search(
            [('membership_status', '=', 'active')]
        )
        for rec in self:
            rec.member_ids = [(4, aff.id) for aff in active_affiliates]
