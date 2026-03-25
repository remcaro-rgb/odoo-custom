from odoo import fields, models


class ClubSwimmingPool(models.Model):
    _name = 'club.swimming.pool'
    _description = 'Swimming Pool'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    pool_type = fields.Selection(
        [
            ('olympic', 'Olympic'),
            ('recreational', 'Recreational'),
            ('kids', 'Kids'),
            ('therapy', 'Therapy'),
        ],
        string='Pool Type',
        required=True,
        default='recreational',
    )
    lane_count = fields.Integer(string='Lane Count')
    max_capacity = fields.Integer(string='Max Capacity')
    under_maintenance = fields.Boolean(string='Under Maintenance', default=False)
    notes = fields.Text(string='Notes')
    lane_ids = fields.One2many(
        'club.swimming.lane', 'pool_id', string='Lanes',
    )
