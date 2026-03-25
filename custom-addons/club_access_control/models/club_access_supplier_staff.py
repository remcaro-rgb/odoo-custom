from odoo import fields, models


class ClubAccessSupplierStaff(models.Model):
    _name = 'club.access.supplier.staff'
    _description = 'Club Access Supplier Staff'
    _order = 'name'

    supplier_id = fields.Many2one(
        'club.access.supplier',
        string='Supplier',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='Full Name', required=True)
    identification_type = fields.Selection(
        [
            ('cc', 'CC - Cedula de Ciudadania'),
            ('ce', 'CE - Cedula de Extranjeria'),
            ('passport', 'Passport'),
            ('other', 'Other'),
        ],
        string='Identification Type',
        default='cc',
    )
    identification_number = fields.Char(
        string='Identification Number',
        required=True,
    )
    phone = fields.Char(string='Phone')
    photo = fields.Binary(string='Photo', attachment=True)
    status = fields.Selection(
        [
            ('active', 'Active'),
            ('suspended', 'Suspended'),
            ('inactive', 'Inactive'),
        ],
        string='Status',
        default='active',
        required=True,
    )
    notes = fields.Text(string='Notes')
