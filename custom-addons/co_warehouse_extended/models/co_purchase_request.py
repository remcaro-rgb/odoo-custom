from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CoPurchaseRequest(models.Model):
    _name = 'co.purchase.request'
    _description = 'Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Request Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    date_request = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    date_approved = fields.Date(
        string='Approval Date',
        readonly=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    line_ids = fields.One2many(
        'co.purchase.request.line',
        'request_id',
        string='Request Lines',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rfq_sent', 'RFQs Sent'),
        ('quotation_compared', 'Quotations Compared'),
        ('purchase', 'Purchase Order Created'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, string='Status')
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'co_purchase_request_id',
        string='Purchase Orders',
    )
    purchase_order_count = fields.Integer(
        string='Purchase Order Count',
        compute='_compute_purchase_order_count',
    )
    notes = fields.Html(string='Notes')
    reason = fields.Text(string='Justification')
    priority = fields.Selection(
        [
            ('0', 'Normal'),
            ('1', 'Urgent'),
            ('2', 'Very Urgent'),
        ],
        string='Priority',
        default='0',
        tracking=True,
    )
    estimated_amount = fields.Float(
        string='Estimated Amount',
        compute='_compute_estimated_amount', store=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True)
    approval_line_ids = fields.One2many(
        'co.purchase.approval.line', 'purchase_request_id',
        string='Approval Steps')
    approval_state = fields.Selection([
        ('no_approval', 'No Approval Needed'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], compute='_compute_approval_state', store=True, string='Approval Status')
    supplier_count = fields.Integer(
        string='Number of Suppliers for RFQ',
        help='Override company default. 0 = use company setting.')
    comparison_id = fields.Many2one(
        'co.quotation.comparison', string='Quotation Comparison',
        readonly=True, copy=False)
    product_request_id = fields.Many2one(
        'co.product.request', string='Source Product Request',
        readonly=True, copy=False)

    @api.depends('line_ids.subtotal')
    def _compute_estimated_amount(self):
        for rec in self:
            rec.estimated_amount = sum(rec.line_ids.mapped('subtotal'))

    @api.depends('approval_line_ids.state')
    def _compute_approval_state(self):
        for rec in self:
            lines = rec.approval_line_ids
            if not lines:
                rec.approval_state = 'no_approval'
            elif any(l.state == 'rejected' for l in lines):
                rec.approval_state = 'rejected'
            elif all(l.state == 'approved' for l in lines):
                rec.approval_state = 'approved'
            else:
                rec.approval_state = 'pending'

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'co.purchase.request'
                ) or _('New')
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Please add at least one product line.'))
            rec._create_approval_lines()
            if rec.approval_state in ('no_approval', 'approved'):
                rec.state = 'approved'
                rec.date_approved = fields.Date.today()
                rec.approver_id = self.env.user
            else:
                rec.state = 'submitted'

    def _create_approval_lines(self):
        self.ensure_one()
        self.approval_line_ids.unlink()
        ApprovalLevel = self.env['co.purchase.approval.level']
        amount = self.estimated_amount
        domain = [
            ('company_id', '=', self.company_id.id),
            ('department_id', '=', self.department_id.id),
            '|',
            ('max_amount', '=', 0),
            ('max_amount', '>=', amount),
            ('min_amount', '<=', amount),
        ]
        levels = ApprovalLevel.search(domain, order='sequence')
        if not levels and self.department_id:
            domain = [
                ('company_id', '=', self.company_id.id),
                ('department_id', '=', False),
                '|',
                ('max_amount', '=', 0),
                ('max_amount', '>=', amount),
                ('min_amount', '<=', amount),
            ]
            levels = ApprovalLevel.search(domain, order='sequence')
        for level in levels:
            self.env['co.purchase.approval.line'].create({
                'purchase_request_id': self.id,
                'approval_level_id': level.id,
            })

    def action_approve(self):
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == 'pending')
        if not pending:
            raise UserError(_('No pending approval steps.'))
        current = pending.sorted('sequence')[0]
        if self.env.user not in current.approval_level_id.approver_ids:
            raise UserError(_(
                'You are not authorized to approve at level "%s".',
                current.approval_level_id.name))
        current.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
            'date': fields.Datetime.now(),
        })
        if self.approval_state == 'approved':
            self.state = 'approved'
            self.date_approved = fields.Date.today()
            self.approver_id = self.env.user

    def action_reject(self):
        self.ensure_one()
        pending = self.approval_line_ids.filtered(
            lambda l: l.state == 'pending')
        if not pending:
            raise UserError(_('No pending approval steps.'))
        current = pending.sorted('sequence')[0]
        if self.env.user not in current.approval_level_id.approver_ids:
            raise UserError(_(
                'You are not authorized to reject at level "%s".',
                current.approval_level_id.name))
        current.write({
            'state': 'rejected',
            'approver_id': self.env.user.id,
            'date': fields.Datetime.now(),
        })
        self.state = 'cancel'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'purchase':
                raise UserError(_(
                    'Cannot cancel a request that already has purchase orders. '
                    'Cancel the purchase orders first.'
                ))
            rec.write({'state': 'cancel'})

    def action_draft(self):
        for rec in self:
            rec.write({'state': 'draft'})

    def action_create_purchase_order(self):
        """Convert approved purchase request into one or more POs grouped by supplier."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved requests can be converted to purchase orders.'))

        # Group lines by supplier
        supplier_lines = {}
        for line in self.line_ids:
            if not line.supplier_id:
                raise UserError(_(
                    'Line "%s" has no supplier. Please set a supplier on all lines '
                    'before creating a purchase order.'
                ) % line.product_id.display_name)
            supplier_lines.setdefault(line.supplier_id.id, []).append(line)

        created_orders = self.env['purchase.order']

        for supplier_id, lines in supplier_lines.items():
            po_vals = {
                'partner_id': supplier_id,
                'co_purchase_request_id': self.id,
                'origin': self.name,
                'company_id': self.company_id.id,
            }
            po = self.env['purchase.order'].create(po_vals)

            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': po.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.quantity,
                    'product_uom': line.product_uom_id.id,
                    'price_unit': line.estimated_price,
                    'name': line.product_id.display_name,
                })

            created_orders |= po

        self.write({'state': 'purchase'})

        if len(created_orders) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'res_id': created_orders.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'domain': [('id', 'in', created_orders.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'domain': [('co_purchase_request_id', '=', self.id)],
            'view_mode': 'list,form',
            'name': _('Purchase Orders'),
            'target': 'current',
        }

    def action_done(self):
        for rec in self:
            rec.write({'state': 'done'})
