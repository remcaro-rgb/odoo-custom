from odoo import api, fields, models


class ClubAffiliateBillingInvoice(models.Model):
    _name = 'club.affiliate.billing.invoice'
    _description = 'Affiliate Billing Invoice'
    _order = 'id desc'

    billing_run_id = fields.Many2one(
        'club.affiliate.billing.run',
        string='Billing Run',
        required=True,
        ondelete='cascade',
    )
    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        required=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        related='affiliate_id.partner_id',
        store=True,
    )
    pos_order_ids = fields.Many2many(
        'pos.order',
        'club_billing_invoice_pos_order_rel',
        'billing_invoice_id',
        'pos_order_id',
        string='POS Orders',
        compute='_compute_pos_order_ids',
        store=True,
    )
    order_count = fields.Integer(
        compute='_compute_order_count',
        string='Order Count',
    )
    total_amount = fields.Float(
        compute='_compute_total_amount',
        store=True,
        string='Total Amount',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
    )
    invoice_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('invoiced', 'Invoiced'),
            ('error', 'Error'),
        ],
        default='pending',
        string='Invoice Status',
    )
    error_message = fields.Char(string='Error Message')
    line_ids = fields.One2many(
        'club.affiliate.billing.line',
        'billing_invoice_id',
        string='Billing Lines',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('line_ids', 'line_ids.pos_order_id')
    def _compute_pos_order_ids(self):
        for rec in self:
            rec.pos_order_ids = rec.line_ids.mapped('pos_order_id')

    @api.depends('pos_order_ids')
    def _compute_order_count(self):
        for rec in self:
            rec.order_count = len(rec.pos_order_ids)

    @api.depends('line_ids', 'line_ids.amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))
