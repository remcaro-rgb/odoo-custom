from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ClubPqrRequest(models.Model):
    _name = 'club.pqr.request'
    _description = 'PQR Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Number',
        readonly=True,
        copy=False,
        default='/',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        required=True,
        string='Affiliate',
        ondelete='restrict',
    )
    category_id = fields.Many2one(
        'club.pqr.category',
        string='Category',
    )
    request_type = fields.Selection(
        [
            ('petition', 'Petition'),
            ('complaint', 'Complaint'),
            ('claim', 'Claim'),
        ],
        string='Type',
        required=True,
        default='petition',
    )
    subject = fields.Char(required=True, string='Subject')
    description = fields.Html(string='Description')
    priority = fields.Selection(
        [
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        string='Priority',
        default='medium',
    )
    status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('resolved', 'Resolved'),
            ('closed', 'Closed'),
            ('rejected', 'Rejected'),
        ],
        default='draft',
        tracking=True,
        string='Status',
    )
    assigned_to = fields.Many2one(
        'res.users',
        string='Assigned To',
    )
    submit_date = fields.Date(string='Submit Date')
    due_date = fields.Date(
        string='Due Date',
        compute='_compute_due_date',
        store=True,
    )
    resolution_date = fields.Date(string='Resolution Date')
    resolution_notes = fields.Html(string='Resolution Notes')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'club_pqr_request_attachment_rel',
        'request_id',
        'attachment_id',
        string='Attachments',
    )
    is_overdue = fields.Boolean(
        string='Overdue',
        compute='_compute_is_overdue',
        search='_search_is_overdue',
    )

    # ---- Computed fields ----------------------------------------------------

    @api.depends('submit_date', 'category_id', 'category_id.sla_days')
    def _compute_due_date(self):
        for rec in self:
            if rec.submit_date and rec.category_id:
                rec.due_date = rec.submit_date + timedelta(
                    days=rec.category_id.sla_days
                )
            else:
                rec.due_date = False

    @api.depends('due_date', 'status')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            if (
                rec.due_date
                and today > rec.due_date
                and rec.status not in ('resolved', 'closed', 'rejected')
            ):
                rec.is_overdue = True
            else:
                rec.is_overdue = False

    def _search_is_overdue(self, operator, value):
        if operator not in ('=', '!='):
            raise UserError(_('Unsupported operator for is_overdue search.'))
        today = fields.Date.today()
        positive = (operator == '=' and value) or (operator == '!=' and not value)
        if positive:
            return [
                ('due_date', '<', today),
                ('status', 'not in', ['resolved', 'closed', 'rejected']),
            ]
        return [
            '|',
            ('due_date', '>=', today),
            ('due_date', '=', False),
        ]

    # ---- CRUD overrides -----------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'club.pqr.request'
                ) or '/'
        return super().create(vals_list)

    # ---- Workflow actions ---------------------------------------------------

    def action_submit(self):
        for rec in self:
            if rec.status != 'draft':
                raise UserError(
                    _('Only draft requests can be submitted.')
                )
            vals = {
                'status': 'submitted',
                'submit_date': fields.Date.today(),
            }
            if rec.category_id and rec.category_id.responsible_id:
                vals['assigned_to'] = rec.category_id.responsible_id.id
            rec.write(vals)

    def action_assign(self):
        for rec in self:
            if rec.status != 'submitted':
                raise UserError(
                    _('Only submitted requests can be assigned.')
                )
            rec.status = 'in_progress'

    def action_resolve(self):
        for rec in self:
            if rec.status != 'in_progress':
                raise UserError(
                    _('Only in-progress requests can be resolved.')
                )
            rec.write({
                'status': 'resolved',
                'resolution_date': fields.Date.today(),
            })

    def action_close(self):
        for rec in self:
            if rec.status != 'resolved':
                raise UserError(
                    _('Only resolved requests can be closed.')
                )
            rec.status = 'closed'

    def action_reject(self):
        for rec in self:
            if rec.status not in ('submitted', 'in_progress'):
                raise UserError(
                    _('Only submitted or in-progress requests can be rejected.')
                )
            rec.status = 'rejected'
