from odoo import fields, models


class ClubAccessCheckpoint(models.Model):
    _name = 'club.access.checkpoint'
    _description = 'Club Access Checkpoint'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    location = fields.Char(string='Location')
    checkpoint_type = fields.Selection(
        [
            ('main_gate', 'Main Gate'),
            ('parking', 'Parking'),
            ('pool_area', 'Pool Area'),
            ('sports_area', 'Sports Area'),
            ('service_entrance', 'Service Entrance'),
            ('other', 'Other'),
        ],
        string='Checkpoint Type',
        default='main_gate',
    )
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
