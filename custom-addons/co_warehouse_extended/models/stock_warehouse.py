from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsible Person',
        help='Person responsible for this warehouse.',
        tracking=True,
    )
    warehouse_type = fields.Selection(
        [
            ('main', 'Main Warehouse'),
            ('transit', 'Transit Warehouse'),
            ('consignment', 'Consignment Warehouse'),
        ],
        string='Warehouse Type',
        default='main',
        help='Classification of the warehouse for operational purposes.',
        tracking=True,
    )
    warehouse_notes = fields.Text(
        string='Warehouse Notes',
    )
    purchase_split_mode = fields.Selection([
        ('auto', 'Automatic Split'),
        ('manual', 'User Decides'),
        ('company_default', 'Use Company Setting'),
    ], string='Stock Availability Split Mode', default='company_default',
        help='Override company setting for this warehouse.')
