from odoo import fields, models


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    cargo_socio_signature = fields.Binary(string='Client Signature')
    cargo_socio_receipt_scan = fields.Binary(string='Signed Receipt Scan')
    cargo_socio_receipt_filename = fields.Char(string='Receipt Filename')
