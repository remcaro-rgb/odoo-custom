from odoo import fields, models


class ClubGolfCaddie(models.Model):
    _name = 'club.golf.caddie'
    _inherit = ['club.caddie.mixin']
    _description = 'Golf Caddie'
    _rec_name = 'partner_id'

    availability_ids = fields.One2many(
        'club.golf.caddie.availability', 'caddie_id',
        string='Availability',
    )
    tee_time_ids = fields.One2many(
        'club.golf.tee.time', 'caddie_id',
        string='Tee Times',
    )


class ClubGolfCaddieAvailability(models.Model):
    _name = 'club.golf.caddie.availability'
    _description = 'Golf Caddie Availability'

    caddie_id = fields.Many2one(
        'club.golf.caddie', required=True, ondelete='cascade',
        string='Caddie',
    )
    day_of_week = fields.Selection(
        [
            ('0', 'Monday'),
            ('1', 'Tuesday'),
            ('2', 'Wednesday'),
            ('3', 'Thursday'),
            ('4', 'Friday'),
            ('5', 'Saturday'),
            ('6', 'Sunday'),
        ],
        required=True,
        string='Day of Week',
    )
    time_from = fields.Float(string='Available From')
    time_to = fields.Float(string='Available Until')
