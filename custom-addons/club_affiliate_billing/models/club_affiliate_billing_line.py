from odoo import fields, models


class ClubAffiliateBillingLine(models.Model):
    _name = 'club.affiliate.billing.line'
    _description = 'Affiliate Billing Line'
    _order = 'order_date asc, id asc'

    billing_invoice_id = fields.Many2one(
        'club.affiliate.billing.invoice',
        string='Billing Invoice',
        required=True,
        ondelete='cascade',
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
    )
    order_date = fields.Datetime(
        string='Order Date',
        related='pos_order_id.date_order',
        store=True,
    )
    order_ref = fields.Char(
        string='Order Reference',
        related='pos_order_id.pos_reference',
        store=True,
    )
    amount = fields.Float(
        string='Amount',
    )
    description = fields.Char(
        string='Description',
    )
