from odoo import fields, models


class ClubAccessVehicle(models.Model):
    _name = 'club.access.vehicle'
    _description = 'Club Access Vehicle'
    _order = 'plate_number'
    _rec_name = 'plate_number'

    affiliate_id = fields.Many2one(
        'club.affiliate',
        string='Affiliate',
        required=True,
        ondelete='cascade',
        index=True,
    )
    plate_number = fields.Char(
        string='Plate Number',
        required=True,
        index=True,
    )
    vehicle_type = fields.Selection(
        [
            ('car', 'Car'),
            ('motorcycle', 'Motorcycle'),
            ('bicycle', 'Bicycle'),
            ('other', 'Other'),
        ],
        string='Vehicle Type',
        default='car',
    )
    brand = fields.Char(string='Brand')
    model = fields.Char(string='Model')
    color = fields.Char(string='Color')
    year = fields.Char(string='Year')
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        (
            'plate_number_uniq',
            'UNIQUE(plate_number)',
            'Plate number must be unique.',
        ),
    ]
