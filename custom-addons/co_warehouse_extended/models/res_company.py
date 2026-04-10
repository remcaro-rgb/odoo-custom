from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    purchase_split_mode = fields.Selection([
        ('auto', 'Automatic Split'),
        ('manual', 'User Decides'),
    ], string='Stock Availability Split Mode', default='auto',
        help='How to handle partially available stock on product requests.')
    default_supplier_count = fields.Integer(
        string='Default Supplier Count for RFQs', default=3,
        help='Number of top-ranked suppliers to request quotations from.')
    supplier_weight_price = fields.Float(string='Price Weight', default=40.0)
    supplier_weight_delivery = fields.Float(string='Delivery Weight', default=25.0)
    supplier_weight_quality = fields.Float(string='Quality Weight', default=20.0)
    supplier_weight_compliance = fields.Float(string='Compliance Weight', default=15.0)
    purchase_journal_mode = fields.Selection([
        ('auto_entry', 'Automatic Journal Entry'),
        ('vendor_bill', 'Vendor Bill'),
    ], string='Receipt Journal Mode', default='vendor_bill',
        help='How to create accounting entries upon goods receipt.')
