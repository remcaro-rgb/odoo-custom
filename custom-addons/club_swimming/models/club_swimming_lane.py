from odoo import fields, models


class ClubSwimmingLane(models.Model):
    _name = 'club.swimming.lane'
    _description = 'Swimming Lane'
    _order = 'pool_id, name'

    pool_id = fields.Many2one(
        'club.swimming.pool', required=True, ondelete='cascade',
        string='Pool',
    )
    name = fields.Char(string='Name', required=True)
    lane_type = fields.Selection(
        [
            ('free_swim', 'Free Swim'),
            ('lap', 'Lap'),
            ('reserved', 'Reserved'),
            ('class', 'Class'),
        ],
        string='Lane Type',
        required=True,
        default='free_swim',
    )
    status = fields.Selection(
        [
            ('available', 'Available'),
            ('occupied', 'Occupied'),
            ('maintenance', 'Maintenance'),
        ],
        string='Status',
        required=True,
        default='available',
    )
