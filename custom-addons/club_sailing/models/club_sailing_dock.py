from odoo import fields, models


class ClubSailingDock(models.Model):
    _name = 'club.sailing.dock'
    _description = 'Sailing Dock'
    _order = 'name'

    name = fields.Char(string='Dock Name', required=True)
    location = fields.Char(string='Location')
    capacity = fields.Integer(string='Boat Capacity')
    under_maintenance = fields.Boolean(string='Under Maintenance', default=False)
    notes = fields.Text(string='Notes')
