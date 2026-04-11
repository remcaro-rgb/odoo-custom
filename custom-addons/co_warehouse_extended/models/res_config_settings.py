from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchase_split_mode = fields.Selection(
        related='company_id.purchase_split_mode', readonly=False)
    purchase_supplier_count = fields.Integer(
        related='company_id.default_supplier_count', readonly=False)
    supplier_weight_price = fields.Float(
        related='company_id.supplier_weight_price', readonly=False)
    supplier_weight_delivery = fields.Float(
        related='company_id.supplier_weight_delivery', readonly=False)
    supplier_weight_quality = fields.Float(
        related='company_id.supplier_weight_quality', readonly=False)
    supplier_weight_compliance = fields.Float(
        related='company_id.supplier_weight_compliance', readonly=False)
    purchase_journal_mode = fields.Selection(
        related='company_id.purchase_journal_mode', readonly=False)
