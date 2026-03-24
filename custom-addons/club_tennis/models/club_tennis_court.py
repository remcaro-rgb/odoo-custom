from odoo import fields, models


class ClubTennisCourt(models.Model):
    _name = 'club.tennis.court'
    _description = 'Tennis Court'
    _rec_name = 'name'

    name = fields.Char(string='Court Name', required=True)
    surface = fields.Selection(
        [
            ('clay', 'Clay'),
            ('hard', 'Hard'),
            ('grass', 'Grass'),
            ('artificial', 'Artificial'),
        ],
        string='Surface',
        required=True,
        default='hard',
    )
    indoor = fields.Boolean(string='Indoor', default=False)
    under_maintenance = fields.Boolean(string='Under Maintenance', default=False)
    booking_ids = fields.One2many(
        'club.tennis.booking', 'court_id', string='Bookings',
    )
