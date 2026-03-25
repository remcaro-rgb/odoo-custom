from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_cargo_socio = fields.Boolean(
        string='Cargo a Socio',
        default=False,
        help='If enabled, this payment method charges the affiliate member account. '
             'Only usable when the customer is a club affiliate with active membership.',
    )
    cargo_socio_account_id = fields.Many2one(
        'account.account',
        string='Affiliate Payable Account',
        help='Account used for "Cargo a Socio" entries (e.g. Cuentas por Cobrar a Socios). '
             'Debit this account when charging to affiliate.',
    )

    @api.onchange('is_cargo_socio', 'cargo_socio_account_id')
    def _onchange_cargo_socio(self):
        if self.is_cargo_socio and self.cargo_socio_account_id:
            self.split_transactions = True
            self.receivable_account_id = self.cargo_socio_account_id

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        fields.append('is_cargo_socio')
        return fields
