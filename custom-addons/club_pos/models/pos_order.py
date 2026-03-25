from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    has_cargo_socio = fields.Boolean(
        compute='_compute_has_cargo_socio',
        store=True,
        help='True if any payment uses Cargo a Socio method.',
    )
    cargo_socio_signature = fields.Binary(string='Client Signature')
    cargo_socio_receipt_scan = fields.Binary(
        string='Signed Receipt Scan',
        attachment=True,
    )
    cargo_socio_receipt_filename = fields.Char()

    @api.depends('payment_ids.payment_method_id.is_cargo_socio')
    def _compute_has_cargo_socio(self):
        for order in self:
            order.has_cargo_socio = any(
                p.payment_method_id.is_cargo_socio for p in order.payment_ids
            )

    def action_pos_order_paid(self):
        """Validate that Cargo a Socio is only used for active affiliates."""
        for order in self:
            cargo_payments = order.payment_ids.filtered(
                lambda p: p.payment_method_id.is_cargo_socio
            )
            if cargo_payments:
                if not order.partner_id:
                    raise UserError(_(
                        'Cargo a Socio requires a customer. '
                        'Please select an affiliate.'
                    ))
                affiliate = self.env['club.affiliate'].search([
                    ('partner_id', '=', order.partner_id.id),
                    ('membership_status', '=', 'active'),
                ], limit=1)
                if not affiliate:
                    raise UserError(_(
                        'Customer "%s" is not an active club affiliate. '
                        'Cargo a Socio can only be used for active affiliates.',
                        order.partner_id.name,
                    ))
        return super().action_pos_order_paid()
