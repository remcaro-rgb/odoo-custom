from odoo import fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    cargo_socio_billed = fields.Boolean(
        string='Cargo a Socio Billed',
        default=False,
        help='True if this order has been included in a monthly billing run.',
    )
    cargo_socio_billing_invoice_id = fields.Many2one(
        'club.affiliate.billing.invoice',
        string='Billing Invoice',
    )
