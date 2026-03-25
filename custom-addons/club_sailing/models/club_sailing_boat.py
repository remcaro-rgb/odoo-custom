from odoo import fields, models


class ClubSailingBoat(models.Model):
    _name = 'club.sailing.boat'
    _description = 'Sailing Boat'
    _order = 'name'

    name = fields.Char(string='Boat Name', required=True)
    boat_type = fields.Selection(
        [
            ('sailboat', 'Sailboat'),
            ('motorboat', 'Motorboat'),
            ('kayak', 'Kayak'),
            ('catamaran', 'Catamaran'),
        ],
        required=True,
        string='Boat Type',
    )
    capacity = fields.Integer(string='Max Passengers', required=True)
    owner_type = fields.Selection(
        [
            ('club', 'Club'),
            ('affiliate', 'Affiliate'),
        ],
        default='club',
        required=True,
        string='Owner Type',
    )
    owner_id = fields.Many2one(
        'club.affiliate',
        string='Owner',
    )
    registration_number = fields.Char(string='Registration Number')
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('in_use', 'In Use'),
            ('maintenance', 'Maintenance'),
        ],
        default='available',
        required=True,
        string='Status',
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('registration_number_uniq', 'unique(registration_number)',
         'Registration number must be unique.'),
    ]
