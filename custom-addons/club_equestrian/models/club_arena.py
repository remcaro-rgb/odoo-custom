from odoo import api, fields, models, _


class ClubArena(models.Model):
    _name = 'club.arena'
    _description = 'Equestrian Arena'
    _rec_name = 'name'

    name = fields.Char(string='Arena Name', required=True)
    arena_type = fields.Selection(
        [
            ('dressage', 'Dressage'),
            ('jumping', 'Jumping'),
            ('outdoor', 'Outdoor'),
            ('multipurpose', 'Multipurpose'),
        ],
        string='Type',
        required=True,
        default='multipurpose',
    )
    capacity = fields.Integer(string='Max Riders', default=1)
    under_maintenance = fields.Boolean(
        string='Under Maintenance',
        default=False,
    )
    booking_ids = fields.One2many(
        'club.equestrian.booking', 'arena_id', string='Bookings'
    )
